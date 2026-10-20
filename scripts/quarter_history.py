"""Fetch ~17 quarters (Jun-22 onward) of revenue/EBITDA/PAT per company from NSE, BOTH bases kept separately -> companydata/_hist/<SYM>.json.
Env: SYMBOLS (optional comma list), SHARD/NSHARDS (split the screened list), SINCE (YYYY-MM-DD, default 2022-06-01). Cached: existing files are skipped."""
import os, sys, json, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "companydata", "_hist"); os.makedirs(H, exist_ok=True)
SINCE = datetime.strptime(os.environ.get("SINCE", "2022-06-01"), "%Y-%m-%d")

def get_json(url, params, ref):
    for k in range(4):
        try:
            r = nse.sess().get(url, params=params, headers=ref, timeout=40)
            return r.json()
        except Exception:
            nse._S["sess"] = None; time.sleep(3 + 4 * k)
    return None

def get_text(url):
    for k in range(3):
        try:
            return nse.sess().get(url, headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        except Exception:
            nse._S["sess"] = None; time.sleep(2 + 3 * k)
    return None

def fetch(sym):
    out = {"C": {}, "S": {}}; stats = {"listed": 0, "parsed": 0, "fail": 0}
    def take(qe, basis, url, when, src):
        k = fd._dt(qe)
        if not k or k < SINCE or k.month not in (3, 6, 9, 12): return
        stats["listed"] += 1
        key = k.strftime("%Y-%m-%d"); cur = out[basis].get(key)
        if cur and (cur["when"] or "") > (when or ""): return
        t = get_text(url); m = fd.parse_xbrl(t) if t else None
        if not m: stats["fail"] += 1; return
        stats["parsed"] += 1; out[basis][key] = dict(m, when=when or "", src=src)
    d = get_json("https://www.nseindia.com/api/integrated-filing-results", {"index": "equities", "symbol": sym}, fd.REF_I)
    for x in ((d or {}).get("data", []) if isinstance(d, dict) else []):
        if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"): continue
        take(x.get("qe_Date"), "C" if x.get("consolidated") == "Consolidated" else "S", x["xbrl"], (x.get("creation_Date") or "")[:11], "int")
    d = get_json("https://www.nseindia.com/api/corporates-financial-results", {"index": "equities", "symbol": sym, "period": "Quarterly"}, fd.REF_L)
    for x in (d if isinstance(d, list) else []):
        if not x.get("xbrl") or x.get("cumulative") not in (None, "Non-cumulative"): continue
        take(x.get("toDate"), "C" if x.get("consolidated") == "Consolidated" else "S", x["xbrl"], (x.get("filingDate") or "")[:11], "leg")
    return out, stats, (d is not None)

syms = [x.strip().upper() for x in os.environ.get("SYMBOLS", "").split(",") if x.strip()]
if not syms and os.environ.get("SYMFILE"):      # JSON of {band: [{symbol,...}]} from universe_bands.py
    u = json.load(open(os.path.join(ROOT, os.environ["SYMFILE"])))
    syms = [r["symbol"] for band in u.values() for r in band]
if not syms:
    syms = [r["symbol"] for r in json.load(open(os.path.join(ROOT, "companydata", "_readiness", "screen.json")))["rows"]]
sh, ns = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARDS", "1"))
syms = [s for i, s in enumerate(syms) if i % ns == sh]
t0 = time.time()
for i, sym in enumerate(syms):
    f = os.path.join(H, sym + ".json")
    if os.path.exists(f): continue
    out, st, ok = fetch(sym)
    if not ok or (st["parsed"] == 0): p(sym, "NO DATA", st, "(not cached)"); continue
    json.dump({"symbol": sym, "C": out["C"], "S": out["S"]}, open(f, "w"))
    p(sym, f"C{len(out['C'])} S{len(out['S'])}", st, f"{time.time()-t0:.0f}s")
publish()
