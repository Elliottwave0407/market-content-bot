"""Read-only probe: what do NSE and BSE return for annual reports? Prints shapes only (no secrets). Writes nothing to the store."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-annual-reports"}
S = requests.Session()
try: S.get("https://www.nseindia.com/companies-listing/corporate-filings-annual-reports", headers={**H, "Accept": "text/html"}, timeout=40)
except Exception as e: p("warm failed", repr(e)[:80])
for sym in ("RELIANCE", "CAPILLARY", "TCS", "KSOLVES"):
    for idx in ("equities", "sme"):
        try:
            r = S.get(f"https://www.nseindia.com/api/annual-reports?index={idx}&symbol={sym}", headers=H, timeout=40)
            js = r.json() if r.text.strip() else None
            rows = js if isinstance(js, list) else (js or {}).get("data", []) if isinstance(js, dict) else []
            p(f"NSE {sym} {idx}: http {r.status_code} rows {len(rows)} keys {sorted(rows[0].keys()) if rows else None}")
            for x in rows[:3]: p("   ", json.dumps(x)[:300])
        except Exception as e:
            p(f"NSE {sym} {idx}: error {repr(e)[:100]}")
        time.sleep(1)
BH = {"User-Agent": H["User-Agent"], "Accept": "application/json, text/plain, */*", "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}
for code in ("500325", "544614", "532540"):
    for url in (f"https://api.bseindia.com/BseIndiaAPI/api/AnnualReport_New/w?scripcode={code}",):
        try:
            r = requests.get(url, headers=BH, timeout=40)
            js = r.json() if r.text.strip() else None
            rows = js.get("Table", js) if isinstance(js, dict) else js
            p(f"BSE {code}: http {r.status_code} rows {len(rows) if isinstance(rows, list) else rows} keys {sorted(rows[0].keys()) if isinstance(rows, list) and rows else None}")
            for x in (rows or [])[:3]: p("   ", json.dumps(x)[:300])
        except Exception as e:
            p(f"BSE {code}: error {repr(e)[:100]}")
        time.sleep(1)
publish()
