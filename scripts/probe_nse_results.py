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
def dtp(x):
    try: return datetime.strptime(x["filingDate"], "%d-%b-%Y %H:%M")
    except Exception: return datetime(2000, 1, 1)
for a_, b_ in (("01-10-2026", "17-10-2026"), ("01-09-2026", "17-10-2026"), ("01-07-2026", "17-10-2026")):
    rs = get(B + "corporates-financial-results?index=equities&period=Quarterly&from_date=%s&to_date=%s" % (a_, b_))
    if isinstance(rs, list) and rs:
        rs.sort(key=dtp, reverse=True)
        p("window", a_, b_, "rows", len(rs), "newest", rs[0]["filingDate"], rs[0]["companyName"], rs[0]["relatingTo"], "E2E:", [x["relatingTo"] for x in rs if x["symbol"] == "E2E"])
    else:
        p("window", a_, b_, "rows", rs if rs is None else len(rs))
rs = get(B + "corporates-financial-results?index=equities&period=Half-Yearly&from_date=01-10-2026&to_date=17-10-2026")
p("half-yearly rows:", len(rs) if isinstance(rs, list) else rs)
ann = get(B + "corporate-announcements?index=equities&symbol=E2E&from_date=15-10-2026&to_date=17-10-2026")
if isinstance(ann, list):
    for x in ann:
        if x["desc"] == "Outcome of Board Meeting":
            p("E2E outcome:", json.dumps({k: x[k] for k in ("an_dt", "attchmntText", "attchmntFile", "hasXbrl", "sm_isin")})[:700])
            break
publish()
