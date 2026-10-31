"""Coverage check for the concall store (read-only on facts; posts nothing).
Lists every earnings-call TRANSCRIPT filing on NSE (equities + SME) day by day, maps each to its BSE code through the ISIN, and checks the store:
  covered           = a stored record for that BSE code within +-5 days
  bse_listed_missing= company also listed on BSE but no stored record (our BSE feed missed it)
  nse_only          = ISIN not on BSE at all (NSE-only company; the BSE feed cannot see it)
Outputs store/concall_coverage/nse_filings.jsonl (cache, resumable per day), missing.jsonl, summary.json. Env: FROM (default 2024-04-01), BUDGET_MIN, WORKERS (fetch day pool, default 2)."""
import os, sys, re, json, time, glob, tempfile, collections
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import store
ROOT = store.ROOT; OUT = os.path.join(ROOT, "concall_coverage"); os.makedirs(OUT, exist_ok=True)
FROM = os.environ.get("FROM") or "2024-04-01"; BUDGET = float(os.environ.get("BUDGET_MIN") or "140"); T0 = time.time()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
     "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
S = requests.Session()
def warm():
    try: S.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", headers={**H, "Accept": "text/html"}, timeout=40)
    except Exception: pass
warm()
CACHE = os.path.join(OUT, "nse_filings.jsonl"); DAYS = os.path.join(OUT, "_days_done.json")
try: days_done = set(json.load(open(DAYS)))
except Exception: days_done = set()
filings = {}
if os.path.exists(CACHE):
    for l in open(CACHE, encoding="utf-8"):
        try: r = json.loads(l); filings[(r["isin"] or r["symbol"], r["day"], r["idx"])] = r
        except Exception: pass
BAD = ("annual general", "agm", "egm", "extra-ordinary", "webinar", "postal ballot", "shareholders meeting")
def is_tr(x):
    t = ((x.get("attchmntText") or "") + " " + (x.get("desc") or "")).lower()
    return "transcript" in t and not any(w in t for w in BAD) and bool(x.get("attchmntFile"))
def fetch(day, idx):
    d = datetime.fromisoformat(day).strftime("%d-%m-%Y")
    url = f"https://www.nseindia.com/api/corporate-announcements?index={idx}&from_date={d}&to_date={d}"
    for attempt in range(4):
        try:
            r = S.get(url, headers=H, timeout=45)
            if r.status_code in (401, 403): warm(); time.sleep(3 * (attempt + 1)); continue
            if r.status_code != 200: time.sleep(3 * (attempt + 1)); continue
            js = r.json(); rows = js if isinstance(js, list) else js.get("data", [])
            return [x for x in rows if is_tr(x)], len(rows)
        except Exception: time.sleep(3 * (attempt + 1))
    return None, 0
d = datetime.fromisoformat(FROM); end = datetime.now(); nfetch = 0; errs = 0; maxrows = 0
while d.date() <= end.date() and (time.time() - T0) / 60 < BUDGET:
    day = d.strftime("%Y-%m-%d")
    if day not in days_done:
        ok = True
        for idx in ("equities", "sme"):
            rows, n = fetch(day, idx)
            if rows is None: ok = False; errs += 1; continue
            maxrows = max(maxrows, n)
            for x in rows:
                k = ((x.get("sm_isin") or x.get("symbol")), day, idx)
                filings[k] = {"symbol": x.get("symbol"), "isin": x.get("sm_isin"), "name": x.get("sm_name"), "day": day, "idx": idx, "url": x.get("attchmntFile"), "text": (x.get("attchmntText") or "")[:120]}
            time.sleep(0.8)
        if ok: days_done.add(day)
        nfetch += 1
        if nfetch % 40 == 0:
            json.dump(sorted(days_done), open(DAYS, "w"))
            with open(CACHE, "w", encoding="utf-8") as fh:
                for r in filings.values(): fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            p("progress", day, "days fetched this run", nfetch, "filings", len(filings), "errors", errs, f"{(time.time()-T0)/60:.0f} min")
    d += timedelta(days=1)
json.dump(sorted(days_done), open(DAYS, "w"))
with open(CACHE, "w", encoding="utf-8") as fh:
    for r in filings.values(): fh.write(json.dumps(r, ensure_ascii=False) + "\n")
total_days = (end.date() - datetime.fromisoformat(FROM).date()).days + 1
p("days done", len(days_done), "of", total_days, "| NSE transcript filings", len(filings), "| max rows in a day", maxrows)

# ---- BSE listing: ISIN -> code
from bse import BSE
isin2code = {}; sym2code = {}; name2code = {}
def nn(x):
    x = re.sub(r"[^a-z0-9 ]+", " ", (x or "").lower())
    x = re.sub(r"\b(limited|ltd|pvt|private|the|india|company|co|corporation|corp|inc)\b", " ", x)
    return re.sub(r"\s+", " ", x).strip()
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for g in ("A", "B", "X", "XT", "T", "Z", "M", "MT", "MS", "P", "R", "F", "IF", "XD", "ZP", "SS", "ST", "Y"):
        try:
            for r in b.listSecurities(group=g):
                c_ = str(r["SCRIP_CD"]).strip()
                if r.get("ISIN_NUMBER"): isin2code[r["ISIN_NUMBER"]] = c_
                if r.get("scrip_id"): sym2code.setdefault(str(r["scrip_id"]).upper(), c_)
                if r.get("Scrip_Name"): name2code.setdefault(nn(r["Scrip_Name"]), c_)
        except Exception: pass
try:
    for c_, v in json.load(open(os.path.join(ROOT, "sector_map", "sector_map.json"))).items():
        for k_ in (v.get("nse_symbol"), v.get("symbol")):
            if k_: sym2code.setdefault(str(k_).upper(), c_)
        if v.get("name"): name2code.setdefault(nn(v["name"]), c_)
except Exception: pass
p("BSE ISINs known:", len(isin2code), "| symbols", len(sym2code), "| names", len(name2code))
# ---- stored records
stored = collections.defaultdict(list); stored_name = collections.defaultdict(list)
for f in glob.glob(os.path.join(ROOT, "concall_facts", "20*.jsonl")):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        stored[str(r["code"])].append((r["day"], bool(r.get("skip"))))
        if r.get("name"): stored_name[nn(r["name"])].append((r["day"], bool(r.get("skip"))))
def near(code, day, tol=5, nm=None):
    dd = datetime.fromisoformat(day)
    for sd, sk in (stored.get(code, []) if code else []) + (stored_name.get(nm, []) if nm else []):
        if abs((datetime.fromisoformat(sd) - dd).days) <= tol: return "skip" if sk else "yes"
    return None
cnt = collections.Counter(); by_m = collections.defaultdict(collections.Counter); miss = []; nse_only = set(); nse_only_sme = set()
for r in filings.values():
    code = isin2code.get(r["isin"]) or sym2code.get((r["symbol"] or "").upper()) or name2code.get(nn(r["name"]))
    n = near(code, r["day"], nm=nn(r["name"]))
    if n == "yes": st = "covered"
    elif n == "skip": st = "covered_but_skipped"
    elif code: st = "bse_listed_missing"
    else: st = "nse_only"; nse_only.add(r["symbol"]); (nse_only_sme.add(r["symbol"]) if r["idx"] == "sme" else None)
    cnt[(st, r["idx"])] += 1; by_m[r["day"][:7]][st] += 1
    if st in ("nse_only", "bse_listed_missing", "covered_but_skipped"): miss.append({**r, "status": st, "bse_code": code})
with open(os.path.join(OUT, "missing.jsonl"), "w", encoding="utf-8") as fh:
    for r in sorted(miss, key=lambda x: x["day"]): fh.write(json.dumps(r, ensure_ascii=False) + "\n")
summ = {"days_done": len(days_done), "total_days": total_days, "nse_filings": len(filings), "status": {f"{a}|{b}": v for (a, b), v in cnt.items()},
        "nse_only_companies": len(nse_only), "nse_only_sme_companies": len(nse_only_sme), "by_month": {m: dict(c) for m, c in sorted(by_m.items())}, "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
json.dump(summ, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
p(json.dumps({k: v for k, v in summ.items() if k != "by_month"}, indent=1))
for m, c in sorted(by_m.items()): p(m, dict(c))
publish()
