import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
try:
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get("https://www.nseindia.com/market-data/live-market-indices", timeout=25)
    r = s.get("https://www.nseindia.com/api/allIndices", headers={"Referer": "https://www.nseindia.com/market-data/live-market-indices"}, timeout=40)
    p("allIndices", r.status_code, len(r.text))
    if r.status_code == 200:
        for x in r.json().get("data", []):
            if "500" in x.get("index", "") or x.get("index") == "NIFTY 50": p({k: x.get(k) for k in ["index", "last", "pe", "pb", "dy", "date"] if k in x} or x)
        p("date:", r.json().get("timestamp"))
except Exception as e: p("ERR", repr(e)[:200])
# archives: historical index PE files
for u in ["https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NIFTY500_Indices_PE_PB_DivYield.csv",
          "https://archives.nseindia.com/content/indices/ind_close_all_27102026.csv"]:
    try:
        r = requests.get(u, headers=UA, timeout=40); p(u[-40:], r.status_code, r.text[:300].replace("\n", " | "))
    except Exception as e: p(u[-30:], "ERR", repr(e)[:80])
publish()
