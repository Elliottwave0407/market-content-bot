import time, collections, requests
from datetime import date, timedelta
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
S.get(H["Referer"], headers={**H, "Accept": "text/html"}, timeout=40)
B = "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly"
def g(q):
    r = S.get(B + q, headers=H, timeout=60); return r.json() if r.status_code == 200 else r.status_code
j = g("")
c = collections.Counter(x["filingDate"][3:11] for x in j); p("default call", len(j), sorted(c.items()))
for a, b in [("01-04-2025", "30-06-2025"), ("01-07-2025", "30-09-2025"), ("01-10-2025", "31-12-2025"), ("01-01-2026", "31-03-2026"), ("01-04-2026", "30-06-2026"), ("01-07-2026", "30-09-2026"), ("01-10-2026", "31-10-2026"), ("01-05-2025", "15-05-2025"), ("10-02-2026", "14-02-2026")]:
    j = g(f"&from_date={a}&to_date={b}")
    if isinstance(j, list): p(a, b, len(j), sorted(collections.Counter(x["filingDate"][3:11] for x in j).items()))
    else: p(a, b, j)
    time.sleep(2)
publish()
