"""Read-only: does NSE's own quote API carry a PE / EPS for SME-series stocks? Prints only field names and PE-like values."""
import os, sys, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
try:
    eps = json.load(open("store/sme_eps/eps2.json"))
    syms = list(eps)
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    seen_keys = None; got = 0; peset = 0; rows = []
    for sym in syms:
        j = None
        for ser in ("ST", "SM", "SZ"):
            try:
                r = s.get(f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series={ser}&symbol={sym}", headers={"Referer": REF}, timeout=40)
                if r.status_code == 200:
                    e = r.json().get("equityResponse", [{}])[0]
                    if e.get("metaData"): j = e; break
            except Exception: pass
            time.sleep(0.4)
        if not j: rows.append((sym, "no data")); continue
        got += 1
        if seen_keys is None:
            seen_keys = {k: (list(v.keys()) if isinstance(v, dict) else type(v).__name__) for k, v in j.items()}
            p("sections and fields:", json.dumps(seen_keys)[:1500])
        flat = {}
        def walk(o, pre=""):
            if isinstance(o, dict):
                for k, v in o.items(): walk(v, pre + k + ".")
            else: flat[pre[:-1]] = o
        walk(j)
        pe = {k: v for k, v in flat.items() if re.search(r"(^|\.)(pe|.*symbolpe|.*eps.*|.*p/?e.*)$", k, re.I)}
        if any(v not in (None, "", "-", 0) for v in pe.values()): peset += 1
        rows.append((sym, pe if pe else "no PE-like field", eps[sym].get("pe"), eps[sym].get("state")))
        time.sleep(0.5)
    p(f"SME symbols {len(syms)} | quote data returned {got} | with a PE/EPS-like value {peset}")
    for r_ in rows[:70]: p("  ", r_)
except Exception as e: p("ERR", repr(e)[:300])
publish()
