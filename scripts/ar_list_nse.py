"""Annual report listing (NSE, equities + SME): one call per symbol to NSE's annual-reports endpoint; keeps filings for FY2023-24 onward (fromYr >= 2023).
Symbol list: NSE's own EQUITY_L / SME_EQUITY_L csv files (+ symbols already seen in our store). Resumable. Cache store/annual_reports/nse_ar.jsonl, state _nse_done.json.
Env BUDGET_MIN (default 120), LIMIT (test: only the first N symbols)."""
import os, sys, io, csv, json, time, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import store
OUT = os.path.join(store.ROOT, "annual_reports"); os.makedirs(OUT, exist_ok=True)
CACHE = os.path.join(OUT, "nse_ar.jsonl"); STATE = os.path.join(OUT, "_nse_done.json")
BUDGET = float(os.environ.get("BUDGET_MIN") or "120"); LIMIT = int(os.environ.get("LIMIT") or "0"); T0 = time.time()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-annual-reports"}
S = requests.Session()
def warm():
    try: S.get("https://www.nseindia.com/companies-listing/corporate-filings-annual-reports", headers={**H, "Accept": "text/html"}, timeout=40)
    except Exception: pass
warm()
syms = {}
for u, kind in (("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", "equities"), ("https://nsearchives.nseindia.com/content/equities/SME_EQUITY_L.csv", "sme")):
    try:
        r = S.get(u, headers=H, timeout=45)
        for row in csv.DictReader(io.StringIO(r.text)):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            s = row.get("SYMBOL")
            if s: syms[s] = {"isin": row.get("ISIN NUMBER"), "name": row.get("NAME OF COMPANY"), "idx": kind}
        p("list", kind, "http", r.status_code, "symbols so far", len(syms))
    except Exception as e: p("list", kind, "error", repr(e)[:80])
for f in glob.glob(os.path.join(store.ROOT, "concall_coverage", "nse_filings.jsonl")) + glob.glob(os.path.join(store.ROOT, "ppt_listing", "nse_ppt.jsonl")):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("symbol") and r["symbol"] not in syms: syms[r["symbol"]] = {"isin": r.get("isin"), "name": r.get("name"), "idx": r.get("idx") or "equities"}
p("symbols total", len(syms))
try: done = set(json.load(open(STATE)))
except Exception: done = set()
if os.environ.get("RESET") == "1": done = set()      # weekly full refresh (new annual reports appear for old symbols)
rows = {}
if os.path.exists(CACHE):
    for l in open(CACHE, encoding="utf-8"):
        try: r = json.loads(l); rows[(r["symbol"], r["fromYr"], r["url"])] = r
        except Exception: pass
todo = [s for s in sorted(syms) if s not in done]
if LIMIT: todo = todo[:LIMIT]
p("todo", len(todo), "done", len(done), "cached rows", len(rows))
def fetch(sym, idx):
    for attempt in range(4):
        try:
            r = S.get(f"https://www.nseindia.com/api/annual-reports?index={idx}&symbol={sym}", headers=H, timeout=40)
            if r.status_code in (401, 403, 429): S.cookies.clear(); warm(); time.sleep(8 * (attempt + 1)); continue
            if r.status_code != 200: time.sleep(2 * (attempt + 1)); continue
            js = r.json() if r.text.strip() else []
            return js if isinstance(js, list) else js.get("data", [])
        except Exception: time.sleep(2 * (attempt + 1))
    return None
n = errs = 0
for sym in todo:
    if (time.time() - T0) / 60 > BUDGET: break
    info = syms[sym]; res = fetch(sym, "equities")
    if res is not None and not res and info.get("idx") == "sme": res = fetch(sym, "sme")
    if res is None: errs += 1; continue
    for x in res:
        try: fy = int(x.get("fromYr") or 0)
        except Exception: fy = 0
        if fy < 2023 or not x.get("fileName"): continue
        rows[(sym, str(fy), x["fileName"])] = {"symbol": sym, "isin": info.get("isin"), "name": x.get("companyName") or info.get("name"), "fromYr": str(fy), "toYr": str(x.get("toYr")), "dt": x.get("disseminationDateTime") or x.get("broadcast_dttm") or x.get("anReportCreateDate"), "url": x["fileName"], "size": x.get("attFileSize")}
    done.add(sym); n += 1
    if n % 100 == 0:
        json.dump(sorted(done), open(STATE, "w")); open(CACHE, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()))
        p("progress", n, "symbols", "rows", len(rows), "errors", errs, f"{(time.time()-T0)/60:.0f} min")
    time.sleep(1.0)
    if n % 120 == 0:
        S.cookies.clear(); warm()      # fresh NSE session every 120 symbols (it started refusing after about 600)
json.dump(sorted(done), open(STATE, "w")); open(CACHE, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()))
p("end: symbols done", len(done), "of", len(syms), "| NSE annual reports FY2023-24 on", len(rows), "| companies", len({r["symbol"] for r in rows.values()}), "| errors", errs)
publish()
