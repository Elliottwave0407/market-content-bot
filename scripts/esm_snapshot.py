"""Snapshot of NSE's live surveillance lists (ESM, ASM long/short term, GSM). Read-only on the exchange; writes store/esm/<kind>_<day>.json only when the list changed since the last snapshot,
so the daily differences (moved to ESM, Stage I->II, II->I, excluded) can be computed later. Posts nothing."""
import os, sys, json, time, glob, hashlib, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
OUT = "store/esm"; os.makedirs(OUT, exist_ok=True)
try:
    s = requests.Session(); s.headers.update(UA)
    s.get("https://www.nseindia.com/", timeout=25)
    s.get("https://www.nseindia.com/regulations/enhanced-surveillance-measure-esm", timeout=25)
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 19800))
    for kind, path in (("esm", "reportESM"), ("asm", "reportASM"), ("gsm", "reportGSM")):
        data = None
        for _t in range(3):
            try:
                r = s.get("https://www.nseindia.com/api/" + path, headers={"Referer": "https://www.nseindia.com/regulations/enhanced-surveillance-measure-esm"}, timeout=40)
                if r.status_code == 200: data = r.json(); break
            except Exception as e:
                p(kind, "retry", type(e).__name__)
            time.sleep(4)
        if data is None: p(kind, "not fetched"); continue
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
        h = hashlib.md5(blob.encode()).hexdigest()
        prev = sorted(glob.glob(f"{OUT}/{kind}_*.json"))
        last_h = None
        if prev:
            try: last_h = json.load(open(prev[-1])).get("hash")
            except Exception: pass
        n = len(data) if isinstance(data, list) else {k: len(v.get("data", [])) for k, v in data.items() if isinstance(v, dict)}
        if h == last_h: p(kind, "unchanged", n); continue
        json.dump({"day": day, "fetched_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "hash": h, "data": data}, open(f"{OUT}/{kind}_{day}.json", "w"), separators=(",", ":"))
        p(kind, "saved", n)
        if kind == "esm" and isinstance(data, list):
            import collections
            p("  ESM stages:", dict(collections.Counter(x.get("esmSurvIndicator") for x in data)), "| dates:", dict(collections.Counter(x.get("esmTime") for x in data).most_common(4)), "| keys:", sorted(data[0].keys()))
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
