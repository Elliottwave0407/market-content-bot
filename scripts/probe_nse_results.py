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
rs = get(B + "corporates-financial-results?index=equities&period=Quarterly")
if isinstance(rs, list):
    def dt(x):
        try: return datetime.strptime(x["filingDate"], "%d-%b-%Y %H:%M")
        except Exception: return datetime(2000, 1, 1)
    rs.sort(key=dt, reverse=True)
    p("newest filing dates:", [x["filingDate"] for x in rs[:5]], "| count since 10 Oct:", sum(1 for x in rs if dt(x) >= datetime(2026, 10, 10)))
    p("sample newest:", json.dumps(rs[0])[:600])
    e = [x for x in rs if x["symbol"] == "E2E"]
    p("E2E result filings:", [(x["relatingTo"], x["toDate"], x["consolidated"], x["filingDate"]) for x in e[:6]])
    x = rs[0]
    if x.get("xbrl"):
        try:
            r = s.get(x["xbrl"], timeout=30)
            p("xbrl", r.status_code, len(r.content))
            import re
            tags = re.findall(r"<(?:in-bse-fin|[a-z\-]+):([A-Za-z]+)[ >]", r.text)
            from collections import Counter
            p("xbrl sample tags:", [t for t, _ in Counter(tags).most_common(60)])
            m = re.findall(r"<in-bse-fin:(RevenueFromOperations|ProfitLossForPeriod|ProfitBeforeTax|BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations|OtherIncome|FinanceCosts|DepreciationDepletionAndAmortisationExpense|Income)[^>]*>([^<]*)<", r.text)
            p("xbrl key values:", m[:12])
        except Exception as e2:
            p("xbrl error", repr(e2)[:100])
ann = get(B + "corporate-announcements?index=equities&from_date=%s&to_date=%s" % (fr, to))
if isinstance(ann, list):
    from collections import Counter
    p("ann desc counts:", Counter(x["desc"] for x in ann).most_common(12))
    e = [x for x in ann if x["symbol"] == "E2E"]
    p("E2E ann desc/time:", [(x["desc"], x["an_dt"]) for x in e])
publish()
