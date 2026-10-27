import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Accept": "application/json,*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/"}
try:
    s = requests.Session(); s.headers.update(H); s.get("https://www.nseindia.com", timeout=30)
    for sym in ["REFRACTORY", "TSCINDIA", "ONYX", "ABMINTLLTD", "RELIANCE"]:
        for ep in ["quote-equity?symbol=", "quote-equity?symbol=%s&section=trade_info#"]:
            pass
        r = s.get(f"https://www.nseindia.com/api/quote-equity?symbol={sym}", timeout=30)
        p(sym, r.status_code, len(r.text))
        if r.status_code == 200:
            j = r.json(); md = j.get("metadata", {}); p("meta", {k: md.get(k) for k in ["symbol", "series", "pdSymbolPe", "pdSectorPe", "pdSectorInd", "industry", "isFNOSec"]})
            ii = j.get("industryInfo", {}); p("industry", ii)
            p("secInfo", {k: j.get("securityInfo", {}).get(k) for k in ["issuedSize", "faceValue", "boardStatus", "tradingStatus"]})
            p("price", {k: j.get("priceInfo", {}).get(k) for k in ["lastPrice", "close"]})
except Exception as e: p("ERR", repr(e)[:200])
publish()
