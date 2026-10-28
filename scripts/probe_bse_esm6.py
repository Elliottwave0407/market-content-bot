"""Read-only: look for a BSE JSON endpoint that serves the current ESM / ASM / GSM lists (BSE site pages), via a warmed browser-like session."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/"}
try:
    s = requests.Session(); s.headers.update(H)
    try: s.get("https://www.bseindia.com/", timeout=25)
    except Exception as e: p("warm", type(e).__name__)
    pages = ["https://www.bseindia.com/markets/equity/EQReports/ESM_Stocks.aspx", "https://www.bseindia.com/markets/equity/EQReports/ASM_GSM_Stocks.aspx", "https://www.bseindia.com/markets/equity/EQReports/esm.aspx", "https://www.bseindia.com/markets/Equity/EQReports/ESMList.aspx"]
    for u in pages:
        try:
            r = s.get(u, timeout=30); t = r.text
            p("PAGE", u.split("/")[-1], r.status_code, len(t), "|", re.sub(r"\s+", " ", t[:150]))
            for m in sorted(set(re.findall(r"(?:api\.bseindia\.com/BseIndiaAPI/api/[A-Za-z0-9_/]+|BseIndiaAPI/api/[A-Za-z0-9_]+)", t)))[:15]: p("   api ref:", m)
        except Exception as e: p("PAGE", u.split("/")[-1], type(e).__name__)
    base = "https://api.bseindia.com/BseIndiaAPI/api/"
    names = ["ESMStageList/w", "ESMList/w", "ESMListData/w", "ESM/w", "GetESMList/w", "ESMStocks/w", "ESMData/w", "ASMGSMList/w", "GetASMGSM/w", "ASMList/w", "GSMList/w", "SurveillanceList/w", "EnhancedSurveillance/w"]
    for n in names:
        try:
            r = s.get(base + n, timeout=25); t = r.text.strip()
            p("API", n, r.status_code, len(t), "|", t[:120].replace("\n", " "))
        except Exception as e: p("API", n, type(e).__name__)
except Exception as e: p("ERR", repr(e)[:300])
publish()
