import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
try:
    seen = set()
    for a, z in (("01-01-2023", "31-12-2023"), ("01-01-2024", "31-12-2024"), ("01-01-2025", "31-12-2025"), ("01-01-2026", "18-10-2026")):
        j = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": "E2E", "from_date": a, "to_date": z}, headers=H, timeout=40).json()
        p("window", a, len(j))
        for x in j:
            d = (x.get("desc") or ""); t = (x.get("attchmntText") or "")
            k = (x.get("an_dt"), d)
            if k in seen: continue
            if "transcript" in t.lower() or "transcript" in d.lower() or "Investor Meet" in d or "Recording" in t:
                seen.add(k)
                p((x.get("an_dt") or "")[:11], "|", d[:45], "|", t[:80].replace("\n", " "), "|", (x.get("attchmntFile") or "")[-45:])
except Exception:
    import traceback; p("ERR", traceback.format_exc()[-600:])
publish()
