import time, collections, requests
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
S.get(H["Referer"], headers={**H, "Accept": "text/html"}, timeout=40)
B = "https://www.nseindia.com/api/corporates-financial-results?"
def g(q):
    r = S.get(B + q, headers=H, timeout=60); return r.json() if r.status_code == 200 else r.status_code
for q in ["index=equities&period=Quarterly&from_date=10-11-2025&to_date=10-11-2025", "index=equities&period=Quarterly&from_date=01-11-2025&to_date=30-11-2025", "index=equities&period=Quarterly&from_date=01-01-2025&to_date=31-03-2025", "index=sme&period=Quarterly", "index=equities&period=Annual"]:
    j = g(q)
    if isinstance(j, list):
        c = collections.Counter(x["filingDate"][3:11] for x in j); fd = sorted({x["toDate"] for x in j})
        p(q[:80], len(j), "filing months", dict(c.most_common(6)), "periods", fd[:3], fd[-3:])
        p("   sample keys", {k: str(j[0][k])[:80] for k in ("xbrl", "resultDetailedDataLink", "params", "relatingTo", "resultDescription", "reInd")} if j else "")
    else: p(q[:80], j)
    time.sleep(2)
publish()
