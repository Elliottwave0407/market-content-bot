import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
try:
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    for sym in ["TSCINDIA", "ONYX", "RELIANCE"]:
        for ep in [f"corporates-financial-results?index=equities&symbol={sym}&period=Quarterly",
                   f"corporates-financial-results?index=equities&symbol={sym}&period=Half-Yearly",
                   f"results-comparision?symbol={sym}",
                   f"quote-equity?symbol={sym}",
                   f"corporates-financial-results?index=sme&symbol={sym}&period=Half-Yearly"]:
            try:
                r = s.get("https://www.nseindia.com/api/" + ep, headers={"Referer": REF}, timeout=40)
                t = r.text[:300].replace("\n", " ")
                p(sym, ep.split("?")[0], ep[-14:], r.status_code, len(r.text), t if r.status_code == 200 else "")
            except Exception as e: p(sym, ep[:30], "ERR", repr(e)[:80])
            time.sleep(1)
except Exception as e: p("ERR", repr(e)[:200])
publish()
