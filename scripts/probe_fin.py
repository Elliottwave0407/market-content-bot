import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
try:
    rows = []
    for extra in ({}, {"from_date": "01-01-2025", "to_date": "18-10-2026"}):
        r = s.get("https://www.nseindia.com/api/corporates-financial-results", params=dict({"index": "equities", "symbol": "E2E", "period": "Quarterly"}, **extra), headers=H, timeout=40)
        j = r.json(); p("variant", list(extra), "n=", len(j))
        for x in j[:14]:
            p(x.get("toDate"), x.get("consolidated"), x.get("audited"), x.get("filingDate"), (x.get("xbrl") or "")[-40:])
        rows += j
    x = next((y for y in rows if y.get("xbrl") and "Consolidated" == y.get("consolidated")), rows[0])
    p("XBRL sample", x.get("toDate"), x.get("xbrl"))
    t = s.get(x["xbrl"], headers=H, timeout=60).text
    p("len", len(t))
    for tag in re.findall(r"<in-bse-fin:([A-Za-z]+)[^>]*>([^<]+)<", t)[:80]:
        if any(k in tag[0] for k in ("Revenue", "Income", "Profit", "Expenses", "Depreciation", "Finance", "Tax", "EarningsPerShare")):
            p(tag[0], tag[1])
except Exception as e:
    import traceback; p("ERR", traceback.format_exc()[-600:])
publish()
