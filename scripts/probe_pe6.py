"""Read-only: other places an EPS/PE for NSE Emerge (SME) stocks might come from. Public data only; nothing stored or posted."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
SYMS = [x for x in os.environ.get("SYMS", "").split(",") if x]
try:
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    def nse(ep):
        try:
            r = s.get("https://www.nseindia.com/api/" + ep, headers={"Referer": REF}, timeout=40)
            return r.status_code, r.text
        except Exception as e: return 0, repr(e)[:80]
    for sym in SYMS[:3]:
        for ep in [f"NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series=ST&symbol={sym}", f"NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series=SM&symbol={sym}",
                   f"NextApi/apiClient/GetQuoteApi?functionName=getSymbolDerivativesData&symbol={sym}", f"NextApi/apiClient/GetQuoteApi?functionName=getSymbolDetails&symbol={sym}", f"NextApi/apiClient/GetQuoteApi?functionName=getFinancialInfo&symbol={sym}"]:
            c, t = nse(ep); p("NSE", sym, ep.split("?")[0].split("/")[-1], ep[-24:], c, len(t), t[:700].replace("\n", " ") if c == 200 else "")
            time.sleep(1)
except Exception as e: p("ERR", repr(e)[:300])
publish()
