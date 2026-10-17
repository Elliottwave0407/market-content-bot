"""Probe: can Actions read NSE's financial-results and announcements feeds? Prints structure and E2E's record (public data)."""
import sys, os, json, time
from datetime import datetime, timedelta
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
s = requests.Session()
s.headers.update(UA)
try:
    r = s.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=25)
    p("home", r.status_code, "cookies", len(s.cookies))
except Exception as e:
    p("home error", repr(e)[:100])

def get(url, **kw):
    try:
        r = s.get(url, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}, timeout=30, **kw)
        p(url.split("?")[0].split("/api/")[-1], r.status_code, len(r.content))
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        p("error", url[:60], repr(e)[:100])
        return None

today = datetime.now()
fr = (today - timedelta(days=4)).strftime("%d-%m-%Y"); to = today.strftime("%d-%m-%Y")
B = "https://www.nseindia.com/api/"
variants = [
  "corporates-financial-results?index=equities&period=Quarterly",
  "corporates-financial-results?index=equities&period=Quarterly&from_date=%s&to_date=%s" % (fr, to),
  "corporates-financial-results?index=equities&period=Quarterly&symbol=E2E",
  "corporates-financial-results?index=equities&symbol=E2E",
  "corporate-announcements?index=equities&from_date=%s&to_date=%s" % (fr, to),
  "corporate-announcements?index=equities&symbol=E2E",
  "corporate-announcements?index=equities&from_date=%s&to_date=%s&symbol=E2E" % (fr, to),
  "corporate-announcements?index=equities",
]
for v in variants:
    d = get(B + v)
    n = len(d) if isinstance(d, list) else (list(d.keys())[:6] if isinstance(d, dict) else None)
    p("  ->", v[:110], "|", n)
    if isinstance(d, list) and d:
        p("     keys:", sorted(d[0].keys()))
        e = [x for x in d if "E2E" in json.dumps(x).upper()]
        p("     E2E rows:", len(e), (json.dumps(e[0])[:800] if e else ""))
        p("     sample:", json.dumps(d[0])[:500])
publish()
