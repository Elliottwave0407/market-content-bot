"""Read-only probe: raw NSE shareholding-pattern rows for one symbol, saved as JSON (nothing is posted)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
SYM = os.environ.get("SYMBOL", "SKYGOLD").strip()
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}
try:
    r = s.get("https://www.nseindia.com/api/corporate-share-holdings-master", params={"index": "equities", "symbol": SYM}, headers=H, timeout=40)
    j = r.json()
    p("status", r.status_code, "rows", len(j))
    if j: p("keys", sorted(j[0].keys()))
    for x in j[:8]: p(json.dumps(x)[:700])
    os.makedirs("companydata/_sh", exist_ok=True)
    json.dump(j, open(f"companydata/_sh/{SYM}.json", "w"), indent=1)
except Exception as e:
    p("err", repr(e)[:200])
publish()
