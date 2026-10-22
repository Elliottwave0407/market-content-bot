"""Read-only probe: can we get sector/industry per company for free? Tries BSE ComHeader and NSE quote-equity industryInfo on a few known companies."""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}
CODES = {"500002": "ABB", "544783": "E2E", "532375": "TIPSMUSIC", "533229": "BAJAJCON", "542652": "POLYCAB", "544253": "KROSS", "500408": "TATAELXSI"}

try:
    for code in CODES:
        for url in (f"https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w?quotetype=EQ&scripcode={code}&seriesid=",
                    f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode={code}"):
            try:
                r = requests.get(url, headers={**UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}, timeout=30)
                p("BSE", code, url.split("/api/")[1].split("?")[0], r.status_code, r.text[:420].replace("\n", " "))
            except Exception as e:
                p("BSE", code, "error", repr(e)[:80])
except Exception:
    p("bse probe error", traceback.format_exc()[-500:])

try:
    s = requests.Session(); s.headers.update(UA)
    s.get("https://www.nseindia.com/", timeout=25)
    s.get("https://www.nseindia.com/get-quotes/equity?symbol=POLYCAB", timeout=25)
    for sym in list(CODES.values())[:6]:
        try:
            r = s.get(f"https://www.nseindia.com/api/quote-equity?symbol={sym}", headers={"Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={sym}"}, timeout=30)
            j = r.json() if r.status_code == 200 else {}
            p("NSE", sym, r.status_code, json.dumps(j.get("industryInfo") or {})[:200], "| keys:", list(j.keys())[:8])
        except Exception as e:
            p("NSE", sym, "error", repr(e)[:80])
        time.sleep(1)
except Exception:
    p("nse probe error", traceback.format_exc()[-500:])
publish()
