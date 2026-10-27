"""SME EPS -> trailing EPS -> PE, for SME stocks in NSE ESM (Stage II PE test). Source: NSE per-symbol announcements (result PDFs); reader: free NVIDIA NIM
lane (nim_read.read_pdf with a half-year prompt; every returned number must be printed in the filing text, else rejected). Scanned PDFs are skipped.
Output store/sme_eps/eps2.json {sym: {"cols": {"end|months|basis": {eps, pat, file}}, "ttm": x|None, "how": text, "price": last close, "pe": x|None, "state": "ok|loss|no_data"}}.
Env: ONLY (comma symbols), MAXN, BUDGET_MIN."""
import os, sys, io, re, json, time, glob, gzip, csv, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import nim_read as nr
from datetime import datetime
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
os.makedirs("store/sme_eps", exist_ok=True)
T0 = time.time(); BUDGET = float(os.environ.get("BUDGET_MIN", "35")) * 60
PROMPT = """You are reading an Indian SME company's financial results filing (PDF text). It is usually HALF-YEARLY (columns: half year ended current, preceding half year, same half last year, then year ended current FY and previous FY), sometimes quarterly or annual.
Find the 'Statement of Profit and Loss' / results table. Return ONLY JSON:
{"unit":"lakh|crore|million|thousand|actual",
 "columns":[{"end":"YYYY-MM-DD","months":6}, ...],   // every numeric column in the printed order: period end date and its length in months (3, 6, 9 or 12)
 "standalone": {"pat":[one number per column], "eps":[one number per column]} or null,
 "consolidated": {same keys} or null}
EPS = basic earnings per share in rupees as printed (negative for losses). pat = net profit/(loss) for the period. Use null for a missing value. Numbers exactly as printed; do not compute or guess. If the statement is not in the text, return {"columns":[],"standalone":null,"consolidated":null}."""
RES = re.compile(r"financial result|results for the|outcome of board meeting|unaudited|audited", re.I)
NOT = re.compile(r"newspaper|earnings call|conference call|investor presentation|trading window|prior intimation|clarification|reply to", re.I)
def add_months(d, m):
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    import calendar; return datetime(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))
def ttm_from(cols):
    """cols: {(end 'YYYY-MM-DD', months): eps}. Returns (ttm, how)."""
    ends = sorted({e for e, m in cols}, reverse=True)
    if not ends: return None, "no columns"
    latest = ends[0]; L = datetime.fromisoformat(latest)
    if (latest, 12) in cols: return cols[(latest, 12)], f"year ended {latest}"
    prev_end = add_months(L, -6).strftime("%Y-%m-%d")
    def near(d, m, tol=3):
        for (e, mm), v in cols.items():
            if mm == m and abs((datetime.fromisoformat(e) - datetime.fromisoformat(d)).days) <= tol: return v
    cur = near(latest, 6) if (latest, 6) in cols or any(m == 6 and abs((datetime.fromisoformat(e) - L).days) <= 3 for e, m in cols) else None
    if cur is None: return None, f"no 6-month column for {latest}"
    prv = near(prev_end, 6)
    if prv is not None: return round(cur + prv, 2), f"half to {latest} + half to {prev_end}"
    fy_prev = near(prev_end, 12); h1_prev = near(add_months(L, -12).strftime("%Y-%m-%d"), 6)
    return None, f"latest half {latest} only"
try:
    ev = sorted(json.load(open("store/esm_history/events.json")), key=lambda e: e["eff"])
    st = {}
    for e in ev: st[e["isin"]] = (e["sym"], {"enter_I": "I", "I_to_II": "II", "II_to_I": "I", "exit": None}[e["ev"]])
    files = sorted(glob.glob("store/prices/d/*_N.csv.gz"))
    px = {}; sme = set()
    for r in csv.reader(gzip.open(files[-1], "rt")):
        px[r[3]] = float(r[8]) if r[8] else None
        if r[4] in ("SM", "ST", "SZ"): sme.add(r[3])
    syms = [v[0] for v in st.values() if v[1] and v[0] in sme]
    only = [x.strip().upper() for x in os.environ.get("ONLY", "").split(",") if x.strip()]
    if only: syms = only
    syms = syms[:int(os.environ.get("MAXN", "300"))]
    p("SME stocks:", len(syms), "| NIM key present:", bool(nr.key()))
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    try: out = json.load(open("store/sme_eps/eps2.json"))
    except Exception: out = {}
    counts = {"ok": 0, "loss": 0, "no_data": 0}
    for k, sym in enumerate(syms):
        if time.time() - T0 > BUDGET: p("budget reached at", k); break
        try:
            r = s.get(f"https://www.nseindia.com/api/corporate-announcements?index=sme&symbol={sym}&from_date=01-04-2025&to_date=28-10-2026", headers={"Referer": REF}, timeout=40)
            j = r.json() if r.status_code == 200 else []
        except Exception: j = []
        cands = [x for x in j if (x.get("attchmntFile") or "").lower().endswith(".pdf") and RES.search((x.get("desc") or "") + " " + (x.get("attchmntText") or "")) and not NOT.search(x.get("desc") or "") and re.search(r"financial result", (x.get("attchmntText") or "") + (x.get("desc") or ""), re.I)]
        cols = {}; reasons = []
        for x in cands[:5]:
            u = x["attchmntFile"]
            try: b = requests.get(u, headers=UA, timeout=60).content
            except Exception: continue
            res, why = nr.read_pdf(b, prompt=PROMPT)
            if not res: reasons.append(why or "?"); continue
            for basis in ("consolidated", "standalone"):
                d = res.get(basis); cl = res.get("columns") or []
                if not isinstance(d, dict) or not d.get("eps"): continue
                for i, c in enumerate(cl):
                    try: e, m = str(c.get("end"))[:10], int(c.get("months"))
                    except Exception: continue
                    ev_ = d["eps"][i] if i < len(d["eps"]) else None
                    if isinstance(ev_, (int, float)): cols[f"{e}|{m}|{basis[:4]}"] = {"eps": ev_, "file": u.split("/")[-1]}
        # choose basis: consolidated if it has the latest column
        ttm = how = None
        for basis in ("cons", "stan"):
            sub = {(kk.split("|")[0], int(kk.split("|")[1])): v["eps"] for kk, v in cols.items() if kk.endswith(basis)}
            if sub:
                ttm, how = ttm_from(sub)
                how = f"{basis}: {how}"
                if ttm is not None: break
        price = px.get(sym)
        state = "no_data" if ttm is None else ("loss" if ttm <= 0 else "ok")
        pe = round(price / ttm, 1) if (ttm and ttm > 0 and price) else None
        out[sym] = {"cols": cols, "ttm": ttm, "how": how, "price": price, "pe": pe, "state": state, "why": reasons[:2], "at": time.strftime("%Y-%m-%d")}
        counts[state] += 1
        p(sym, state, "ttm", ttm, "pe", pe, "|", how, "|", (reasons[:1] or ""))
        if (k + 1) % 10 == 0: json.dump(out, open("store/sme_eps/eps2.json", "w"))
    json.dump(out, open("store/sme_eps/eps2.json", "w"))
    p("SUMMARY", counts)
except Exception:
    p("ERR", traceback.format_exc()[-700:])
publish()
