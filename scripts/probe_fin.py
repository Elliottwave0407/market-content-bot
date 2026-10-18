import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
try:
    for idx in ("sme", "equities"):
        for per in ("Quarterly", "Annual", "Half-Yearly"):
            r = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": idx, "symbol": "E2E", "period": per}, headers=H, timeout=40)
            try: j = r.json()
            except Exception: j = []
            p(idx, per, "n=", len(j), [(x.get("toDate"), x.get("consolidated")[:4]) for x in j[:6]])
    r = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": "E2E", "from_date": "01-01-2025", "to_date": "18-10-2026"}, headers=H, timeout=40)
    j = r.json(); p("announcements", len(j))
    for x in j:
        d = (x.get("desc") or "")
        if "result" in d.lower() or "financial" in d.lower():
            p(x.get("an_dt"), d[:50], (x.get("attchmntText") or "")[:90])
except Exception:
    import traceback; p("ERR", traceback.format_exc()[-600:])
publish()
