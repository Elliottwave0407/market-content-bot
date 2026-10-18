import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
try:
    for u, prm in (("https://www.nseindia.com/api/integrated-filing-results", {"index": "equities", "symbol": "E2E", "period_ended": "all", "type": "Integrated Filing- Financial"}),
                   ("https://www.nseindia.com/api/integrated-filing-results", {"index": "equities", "symbol": "E2E"})):
        r = s.get(u, params=prm, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing"}, timeout=40)
        p(r.status_code, r.text[:200].replace("\n", " "))
        try:
            j = r.json(); d = j.get("data", j) if isinstance(j, dict) else j
            p("n=", len(d)); 
            if d: p("KEYS", list(d[0].keys()))
            for x in d[:8]: p(json.dumps({k: str(v)[:70] for k, v in x.items()})[:420])
        except Exception as e: p("json err", repr(e)[:60])
except Exception:
    import traceback; p("ERR", traceback.format_exc()[-600:])
publish()
