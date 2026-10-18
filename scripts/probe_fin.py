import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
for per in ("Quarterly",):
    try:
        r = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": "E2E", "period": per}, headers=H, timeout=40)
        j = r.json()
        p(per, type(j).__name__, len(j))
        for x in j[:12]:
            p(json.dumps({k: x[k] for k in x if k in ("fromDate","toDate","relatingTo","audited","consolidated","cumulative","filingDate","xbrl","resultDetailedDataLink")})[:300])
        p("KEYS", list(j[0].keys()))
    except Exception as e:
        p("err", repr(e)[:150])
publish()
