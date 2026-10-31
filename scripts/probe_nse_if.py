import time, collections, requests
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-integrated-filing"}
S.get(H["Referer"], headers={**H, "Accept": "text/html"}, timeout=40)
B = "https://www.nseindia.com/api/"
tests = ["integrated-filing-results?index=equities&period_ended=all&type=Integrated%20Filing-%20Financials",
         "integrated-filing-results?index=equities&type=Integrated%20Filing-%20Financials&from_date=01-10-2026&to_date=31-10-2026",
         "integrated-filing-results?index=sme&type=Integrated%20Filing-%20Financials",
         "integrated-filing-results?index=equities&symbol=INFY&type=Integrated%20Filing-%20Financials",
         "corporate-further-issues-integrated-filing?index=equities"]
for t in tests:
    try:
        r = S.get(B + t, headers=H, timeout=60); 
        if r.status_code != 200: p(t[:90], r.status_code); continue
        j = r.json(); rows = j if isinstance(j, list) else (j.get("data") or j.get("rows") or j)
        if isinstance(rows, list):
            p(t[:90], "rows", len(rows), "keys", sorted(rows[0].keys())[:30] if rows else "")
            if rows: p("   sample", {k: str(v)[:70] for k, v in list(rows[0].items())[:18]}); p("   by month", sorted(collections.Counter(str(x.get("broadcast_date") or x.get("filingDate") or x.get("date") or "")[3:11] for x in rows).items())[:14])
        else: p(t[:90], type(rows).__name__, str(rows)[:200])
    except Exception as e: p(t[:90], type(e).__name__, str(e)[:100])
    time.sleep(2)
publish()
