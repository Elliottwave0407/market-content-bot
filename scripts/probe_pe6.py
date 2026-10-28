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
    for ep in ["corporates-financial-results?index=sme&period=Half-Yearly&from_date=01-04-2026&to_date=28-10-2026",
               "corporates-financial-results?index=sme&from_date=01-04-2026&to_date=28-10-2026",
               "corporates-financial-results?index=sme&period=Half-Yearly&from_date=01-10-2025&to_date=31-03-2026",
               "corporates-financial-results?index=sme&period=Annual&from_date=01-04-2026&to_date=28-10-2026",
               "corporates-financial-results?index=sme&period=Quarterly&from_date=01-04-2026&to_date=28-10-2026"]:
        c, t = nse(ep); n = None
        try: j = json.loads(t); n = len(j) if isinstance(j, list) else list(j)[:5]
        except Exception: pass
        p("RESULTS", ep.split("?")[1][:80], c, len(t), "items:", n)
        if c == 200 and isinstance(n, int) and n:
            j = json.loads(t); p("   keys:", list(j[0].keys())[:25]); p("   sample:", {k: j[0].get(k) for k in list(j[0].keys())[:14]})
        time.sleep(1)
    for sym in SYMS[:3]:
        for ep in [f"NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series=EQ&symbol={sym}", f"NextApi/apiClient/GetQuoteApi?functionName=getMetaData&symbol={sym}",
                   f"quote-equity?symbol={sym}&section=trade_info", f"results-comparision?symbol={sym}"]:
            c, t = nse(ep); p("NSE", sym, ep.split("?")[0].split("/")[-1], ep[-24:], c, len(t), t[:160].replace("\n", " ") if c == 200 else "")
            time.sleep(1)
    for sym in SYMS[:3]:
        for url in [f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}.NS?modules=defaultKeyStatistics,summaryDetail,financialData", f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}.NS?range=5d&interval=1d"]:
            try:
                r = requests.get(url, headers=UA, timeout=30); p("YAHOO", sym, url.split("/")[-1][:22], r.status_code, len(r.text), r.text[:140].replace("\n", " "))
            except Exception as e: p("YAHOO", sym, "ERR", repr(e)[:60])
            time.sleep(1)
except Exception as e: p("ERR", repr(e)[:300])
publish()
