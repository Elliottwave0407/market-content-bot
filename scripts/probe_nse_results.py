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
d = get(f"https://www.nseindia.com/api/corporates-financial-results?index=equities&from_date={fr}&to_date={to}&period=Quarterly")
if isinstance(d, list):
    p("results rows:", len(d))
    if d:
        p("keys:", sorted(d[0].keys()))
        p("sample:", json.dumps(d[0])[:700])
    e = [x for x in d if "E2E" in json.dumps(x).upper()]
    p("E2E rows:", len(e))
    for x in e[:2]:
        p("E2E:", json.dumps(x)[:900])
    p("distinct symbols:", len({x.get("symbol") for x in d}), "| consolidated values:", sorted({str(x.get("consolidated")) for x in d}))
elif isinstance(d, dict):
    p("dict keys", list(d.keys())[:10], json.dumps(d)[:300])
a = get(f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={fr}&to_date={to}&subject=Financial%20Results")
if isinstance(a, list):
    p("ann rows:", len(a))
    if a:
        p("ann keys:", sorted(a[0].keys()))
        p("ann sample:", json.dumps(a[0])[:600])
    e = [x for x in a if "E2E" in json.dumps(x).upper()]
    p("ann E2E:", len(e), json.dumps(e[0])[:600] if e else "")
publish()
