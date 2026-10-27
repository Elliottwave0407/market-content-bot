"""EPS for SME stocks in ESM (for the Stage II PE test): NSE per-symbol announcements -> latest result PDFs -> EPS by text rules (no model).
Output store/sme_eps/eps.json {sym: {"rows":[{period, eps, basis, file, ann_date}], "ttm": float|None, "src": "pdf-text"}} + coverage line. Posts nothing.
Env: ONLY (comma symbols, test), MAXN (default 200)."""
import os, sys, io, re, json, time, glob, gzip, csv, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
os.makedirs("store/sme_eps", exist_ok=True)
RES = re.compile(r"financial result|results for the|outcome of board meeting|unaudited|audited", re.I)
NOT = re.compile(r"newspaper|earnings call|conference call|investor presentation|trading window|intimation of board meeting|prior intimation", re.I)
EPS_RX = re.compile(r"(?:earnings?\s*(?:/\(loss\))?\s*per\s*(?:equity\s*)?share|basic\s*(?:and diluted)?\s*eps|\(?basic\)?\s*(?:&|and)?\s*\(?diluted\)?)[^0-9\-\(]{0,120}?(\(?-?\d{1,4}\.\d{1,2}\)?)", re.I)
def num(t):
    t = t.strip(); neg = t.startswith("(") or t.startswith("-")
    v = float(t.strip("()-")); return -v if neg else v
try:
    import pypdf
    ev = sorted(json.load(open("store/esm_history/events.json")), key=lambda e: e["eff"])
    st = {}
    for e in ev: st[e["isin"]] = (e["sym"], {"enter_I": "I", "I_to_II": "II", "II_to_I": "I", "exit": None}[e["ev"]])
    last = sorted(glob.glob("store/prices/d/*_N.csv.gz"))[-1]
    sme = {r[3] for r in csv.reader(gzip.open(last, "rt")) if r[4] in ("SM", "ST", "SZ")}
    syms = [v[0] for v in st.values() if v[1] and v[0] in sme]
    only = [x.strip().upper() for x in os.environ.get("ONLY", "").split(",") if x.strip()]
    if only: syms = only
    syms = syms[:int(os.environ.get("MAXN", "200"))]
    p("SME stocks in ESM:", len(syms))
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    try: out = json.load(open("store/sme_eps/eps.json"))
    except Exception: out = {}
    got = 0; noann = 0; nopdf = 0
    for k, sym in enumerate(syms):
        try:
            r = s.get(f"https://www.nseindia.com/api/corporate-announcements?index=sme&symbol={sym}&from_date=01-04-2025&to_date=28-10-2026", headers={"Referer": REF}, timeout=40)
            j = r.json() if r.status_code == 200 else []
        except Exception: j = []
        cands = [x for x in j if x.get("attchmntFile") and RES.search((x.get("desc") or "") + " " + (x.get("attchmntText") or "")) and not NOT.search(x.get("desc") or "")][:6]
        if not j: noann += 1
        if only:
            p("DEBUG", sym, "announcements", len(j), "| cands", len(cands))
            for x in j[:60]:
                d = (x.get("desc") or "")
                if re.search(r"result|board|financial", d, re.I): p("   ", (x.get("an_dt") or "")[:11], d[:60], "|", (x.get("attchmntFile") or "")[-40:], "|", (x.get("attchmntText") or "")[:80].replace("\n", " "))
        rows = []
        for x in cands:
            u = x["attchmntFile"]
            if not u.lower().endswith(".pdf"): continue
            try:
                b = requests.get(u, headers=UA, timeout=60).content
                t = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(b)).pages[:6])
            except Exception: continue
            t = re.sub(r"\s+", " ", t)
            if only: p("   pdf", u[-30:], "chars", len(t), "| has EPS word:", bool(re.search(r"per share|eps", t, re.I)), "| sample:", t[:120])
            if only:
                for mm in list(re.finditer(r"per\s*(equity\s*)?share|\beps\b", t, re.I))[:3]: p("      ctx:", t[max(0, mm.start() - 60):mm.start() + 260])
            if len(t) < 300 or not re.search(r"half year|six months|quarter|year ended|period ended", t, re.I): continue
            m = EPS_RX.search(t)
            if not m: continue
            per = re.search(r"(?:half[ -]year|six months|quarter|year|period) ended\s*:?\s*([0-9]{1,2}(?:st|nd|rd|th)?[ ,.-]*[A-Za-z]{3,9}[ ,.-]*[0-9]{2,4}|[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})", t, re.I)
            rows.append({"period": per.group(1) if per else None, "eps_first": num(m.group(1)), "ann": x.get("an_dt"), "file": u.split("/")[-1], "desc": (x.get("desc") or "")[:50]})
            time.sleep(0.4)
        if rows: got += 1
        elif j: nopdf += 1
        out[sym] = {"rows": rows, "at": time.strftime("%Y-%m-%d")}
        time.sleep(0.5)
        if (k + 1) % 20 == 0: json.dump(out, open("store/sme_eps/eps.json", "w"))
    json.dump(out, open("store/sme_eps/eps.json", "w"))
    p("with EPS rows:", got, "| announcements but no EPS parsed:", nopdf, "| no announcements:", noann, "of", len(syms))
    for sym in syms[:10]: p(sym, [(r["period"], r["eps_first"]) for r in out[sym]["rows"]][:4])
except Exception:
    p("ERR", traceback.format_exc()[-600:])
publish()
