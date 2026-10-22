"""Read-only: which NSE endpoints carry Havells' numbers right at filing time? Prints keys and the Havells row."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
d = datetime.now(IST).strftime("%d-%m-%Y")
urls = [
 f"https://www.nseindia.com/api/corporates-financial-results?index=equities&from_date={d}&to_date={d}&period=Quarterly",
 f"https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly",
 f"https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=HAVELLS&period=Quarterly",
 f"https://www.nseindia.com/api/results-comparision?symbol=HAVELLS",
 f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=HAVELLS",
]
for u in urls:
    try:
        r = nr.sess().get(u, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}, timeout=40)
        p("URL", u.split("api/")[1][:90], r.status_code, len(r.text))
        if r.status_code != 200 or not r.text.strip(): continue
        j = r.json()
        rows = j if isinstance(j, list) else (j.get("data") or j.get("resCmpData") or [j])
        p("  rows", len(rows), "keys", sorted(rows[0].keys())[:40] if rows and isinstance(rows[0], dict) else str(j)[:200])
        for x in rows:
            if isinstance(x, dict) and "HAVELLS" in json.dumps(x).upper()[:600]:
                p("  HAVELLS:", json.dumps(x)[:1500]); break
    except Exception as e:
        p("ERR", u[:80], repr(e)[:120])
publish()
