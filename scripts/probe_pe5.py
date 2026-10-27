import os, sys, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
try:
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    G = lambda u: s.get("https://www.nseindia.com/api/" + u, headers={"Referer": REF}, timeout=40)
    for sym in ["KORE", "SAAKSHI"]:
        for u in [f"corporates-financial-results?index=sme&symbol={sym}&period=Half-Yearly&from_date=01-01-2025&to_date=28-10-2026",
                  f"corporates-financial-results?index=sme&symbol={sym}&period=Half-Yearly&issuer=&from_date=01-04-2025&to_date=28-10-2026",
                  f"corporates-financial-results-data?index=sme&symbol={sym}&period=Half-Yearly",
                  f"corporate-announcements?index=sme&symbol={sym}&from_date=01-04-2025&to_date=28-10-2026"]:
            r = G(u)
            try: j = r.json()
            except Exception: j = None
            if isinstance(j, list):
                p(sym, u.split("?")[0], r.status_code, len(j), [(x.get("toDate") or x.get("an_dt") or "", (x.get("desc") or x.get("filingDate") or "")[:60]) for x in j[:4]])
            else: p(sym, u.split("?")[0], r.status_code, str(r.text)[:150])
            time.sleep(0.8)
except Exception as e:
    import traceback; p("ERR", traceback.format_exc()[-400:])
publish()
