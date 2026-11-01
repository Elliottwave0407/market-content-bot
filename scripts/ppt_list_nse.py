"""Investor presentation listing (NSE, equities + SME) from 2024-04-01, day by day, resumable. Cache: store/ppt_listing/nse_ppt.jsonl. (adapted from concall_coverage)
"""
_ = """Coverage check for the concall store (read-only on facts; posts nothing).
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
ROOT = store.ROOT; OUT = os.path.join(ROOT, "ppt_listing"); os.makedirs(OUT, exist_ok=True)
FROM = os.environ.get("FROM") or "2024-04-01"; BUDGET = float(os.environ.get("BUDGET_MIN") or "140"); T0 = time.time()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
     "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
S = requests.Session()
def warm():
    try: S.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", headers={**H, "Accept": "text/html"}, timeout=40)
    except Exception: pass
warm()
CACHE = os.path.join(OUT, "nse_ppt.jsonl"); DAYS = os.path.join(OUT, "_days_done.json")
try: days_done = set(json.load(open(DAYS)))
except Exception: days_done = set()
filings = {}
if os.path.exists(CACHE):
    for l in open(CACHE, encoding="utf-8"):
        try: r = json.loads(l); filings[(r["isin"] or r["symbol"], r["day"], r["idx"], r.get("url"))] = r
        except Exception: pass
def is_tr(x):
    d = (x.get("desc") or "").lower(); t = ((x.get("attchmntText") or "") + " " + d).lower()
    return ("investor presentation" in d or "investor presentation" in t or "analyst presentation" in t) and bool(x.get("attchmntFile")) and (x.get("attchmntFile") or "").lower().endswith((".pdf", ".ppt", ".pptx"))
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
                k = ((x.get("sm_isin") or x.get("symbol")), day, idx, x.get("attchmntFile"))
                filings[k] = {"symbol": x.get("symbol"), "isin": x.get("sm_isin"), "name": x.get("sm_name"), "day": day, "idx": idx, "url": x.get("attchmntFile"), "text": (x.get("attchmntText") or "")[:160], "desc": (x.get("desc") or "")[:60], "dt": x.get("an_dt")}
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
p("days done", len(days_done), "of", total_days, "| NSE presentation filings", len(filings), "| max rows in a day", maxrows)


publish()
