import os, json, time, requests
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
S.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", headers={**H, "Accept": "text/html"}, timeout=40)
def get(u):
    try:
        r = S.get(u, headers=H, timeout=45); return r.status_code, (r.json() if r.status_code == 200 else r.text[:80])
    except Exception as e: return "err", type(e).__name__
B = "https://www.nseindia.com/api/"
tests = ["corporates-financial-results?index=equities&period=Quarterly&from_date=01-10-2025&to_date=31-10-2025",
         "corporates-financial-results?index=equities&period=Quarterly",
         "corporates-financial-results?index=equities&period=Quarterly&from_date=01-11-2025&to_date=15-11-2025&res_type=U",
         "corporates-financial-results?index=equities&period=Quarterly&symbol=INFY",
         "results-comparision?symbol=INFY",
         "results-comparision?symbol=ZOTA"]
for t in tests:
    sc, js = get(B + t)
    if isinstance(js, list): p(t[:95], sc, "list", len(js), (sorted(js[0].keys()) if js else ""), ({k: str(v)[:50] for k, v in list(js[0].items())[:16]} if js else ""))
    elif isinstance(js, dict):
        p(t[:95], sc, "dict", list(js.keys())[:8]); 
        for k, v in js.items():
            if isinstance(v, list): p("   ", k, "len", len(v), (sorted(v[0].keys())[:30] if v and isinstance(v[0], dict) else v[:2]), ({kk: str(vv)[:40] for kk, vv in list(v[0].items())[:12]} if v and isinstance(v[0], dict) else ""))
    else: p(t[:95], sc, str(js)[:100])
    time.sleep(2)
publish()
