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
for sym in ("E2E", "SGFIN", "IXIGO"):
    for per in ("Quarterly", "Half-Yearly"):
        rs = get(B + "corporates-financial-results?index=equities&period=%s&symbol=%s" % (per, sym))
        if isinstance(rs, list):
            rows = sorted(((x["toDate"], x["consolidated"], x["filingDate"], bool(x.get("xbrl"))) for x in rs), key=lambda t: datetime.strptime(t[0], "%d-%b-%Y"), reverse=True)
            p(sym, per, len(rs), rows[:4])
b = get(B + "corporate-announcements?index=equities&from_date=16-10-2026&to_date=16-10-2026")
if isinstance(b, list):
    import re
    res = [x for x in b if re.search(r"financial results|results for the (quarter|period|half)", x.get("attchmntText") or "", re.I)]
    p("announcements 16 Oct:", len(b), "| results-like:", len(res))
    from collections import Counter
    p("desc of results-like:", Counter(x["desc"] for x in res).most_common(6))
    p("sample results-like:", [(x["symbol"], x["desc"], (x["attchmntText"] or "")[:90]) for x in res[:4]])
publish()
