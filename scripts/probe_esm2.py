"""Read-only probe 2: try NSE JSON endpoints (cookie session, like the results bot) and BSE API guesses for the ESM/ASM lists, plus the NSE circular PDF format. Sends nothing."""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
try:
    s = requests.Session(); s.headers.update(UA)
    s.get("https://www.nseindia.com/", timeout=25)
    s.get("https://www.nseindia.com/regulations/enhanced-surveillance-measure-esm", timeout=25)
    for path in ("reportESM", "reportASM", "reportGSM", "reportESM?index=esm", "circulars?fromDate=20-10-2026&toDate=27-10-2026&department=SURVEILLANCE", "circulars?isLatest=true&fromDate=20-10-2026&toDate=27-10-2026",
                 "merged-daily-reports?key=favCapital", "historical/esm", "reports?name=ESM", "esm-list", "equity-stockIndices?index=SECURITIES%20IN%20F%26O"):
        try:
            r = s.get("https://www.nseindia.com/api/" + path, headers={"Referer": "https://www.nseindia.com/regulations/enhanced-surveillance-measure-esm"}, timeout=30)
            p("NSE api", path[:60], r.status_code, len(r.text), r.text[:260].replace("\n", " "))
        except Exception as e:
            p("NSE api", path[:50], "error", type(e).__name__)
        time.sleep(1)
except Exception:
    p("nse err", traceback.format_exc()[-400:])
try:
    h = {**UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}
    for path in ("ESMNew/w", "ESM/w", "ESMList/w", "ESMListNew/w", "EnhancedSurveillance/w", "ASMNew/w", "ESMData/w", "getESMData/w"):
        try:
            r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/" + path, headers=h, timeout=30)
            p("BSE api", path, r.status_code, len(r.text), r.text[:200].replace("\n", " "))
        except Exception as e:
            p("BSE api", path, "error", type(e).__name__)
except Exception:
    p("bse err", traceback.format_exc()[-300:])
try:
    r = requests.get("https://nsearchives.nseindia.com/content/circulars/SURV69315.pdf", headers=UA, timeout=40)
    p("circular pdf", r.status_code, len(r.content), r.content[:8])
    import io
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            p("pdf pages", len(pdf.pages), "text:", (pdf.pages[0].extract_text() or "")[:900].replace("\n", " | "))
    except Exception as e:
        p("pdf text error", repr(e)[:80])
except Exception:
    p("circ err", traceback.format_exc()[-300:])
publish()
