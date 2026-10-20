"""Debug (read-only): how many quarters does NSE give per company, by basis? Env SYMBOLS (comma list) or first MAXN screened."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
syms = [x.strip().upper() for x in os.environ.get("SYMBOLS", "").split(",") if x.strip()]
if not syms:
    rows = json.load(open(os.path.join(ROOT, "companydata", "_readiness", "screen.json")))["rows"]
    syms = [r["symbol"] for r in rows][: int(os.environ.get("MAXN", "12"))]
s = nse.sess()
for sym in syms:
    t0 = time.time(); res = {"int_total": None, "int_fin": 0, "int_xbrl": 0, "leg_total": None, "leg_xbrl": 0}; got = {}
    try:
        d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=fd.REF_I, timeout=40).json().get("data", [])
        res["int_total"] = len(d)
    except Exception as e:
        d = []; res["int_total"] = "ERR " + repr(e)[:40]
    for x in d:
        if "Financial" not in (x.get("type") or ""): continue
        res["int_fin"] += 1
        if x.get("xbrl") in (None, "None"): continue
        res["int_xbrl"] += 1
        try:
            m = fd.parse_xbrl(s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text)
        except Exception: m = None
        b = "C" if x.get("consolidated") == "Consolidated" else "S"
        got.setdefault(b, set()).add((fd._dt(x.get("qe_Date")) or 0) and fd._label(fd._dt(x.get("qe_Date"))) + ("" if m else "!parsefail"))
    try:
        d = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": sym, "period": "Quarterly"}, headers=fd.REF_L, timeout=40).json()
        res["leg_total"] = len(d)
    except Exception as e:
        d = []; res["leg_total"] = "ERR " + repr(e)[:40]
    for x in d:
        if not x.get("xbrl") or x.get("cumulative") not in (None, "Non-cumulative"): continue
        res["leg_xbrl"] += 1
        try:
            m = fd.parse_xbrl(s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text)
        except Exception: m = None
        b = "C" if x.get("consolidated") == "Consolidated" else "S"
        dt = fd._dt(x.get("toDate"))
        got.setdefault(b, set()).add((fd._label(dt) if dt else "?") + ("" if m else "!parsefail"))
    p(sym, res, f"{time.time()-t0:.0f}s")
    for b, v in sorted(got.items()): p("   ", b, len(v), sorted(v, key=lambda z: (z[4:6], z[:3])))
publish()
