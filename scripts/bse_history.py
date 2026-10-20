"""Quarter history for companies NSE's results API does not serve (BSE-only / SME), straight from BSE's results tables.
Writes companydata/_hist/<SYM>.json in the same shape as quarter_history.py (values in Rs Crore; BSE tables are in Rs million, so /10 (SHALBY check: 331 Cr)).
Also logs which quarter-ends actually have data (to see whether a company files quarterly or half-yearly).
Env: SYMBOLS, SYMFILE, SHARD/NSHARDS, QFROM (default 114 = Jun-22), QTO (default 133)."""
import os, sys, json, tempfile, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import results_fetcher as rf
from bse import BSE
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "companydata", "_hist"); os.makedirs(HIST, exist_ok=True)
sym2code = {v: k for k, v in json.load(open(os.path.join(ROOT, "state", "symbols.json")))["m"].items()}
syms = [x.strip().upper() for x in (os.environ.get("SYMBOLS") or "").split(",") if x.strip()]
if not syms and os.environ.get("SYMFILE"):
    u = json.load(open(os.path.join(ROOT, os.environ["SYMFILE"])))
    syms = [x["symbol"] for v in u.values() for x in v if not os.path.exists(os.path.join(HIST, x["symbol"] + ".json"))]
sh, nsh = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARDS", "1"))
syms = [s for i, s in enumerate(sorted(set(syms))) if i % nsh == sh]
q0, q1 = int(os.environ.get("QFROM", "114")), int(os.environ.get("QTO", "133"))
def qdate(q):
    lab = rf.qlabel(q); mon = {"Mar": 3, "Jun": 6, "Sep": 9, "Dec": 12}[lab[:3]]; yr = 2000 + int(lab[4:])
    return datetime(yr, mon, 31 if mon in (3, 12) else 30).strftime("%Y-%m-%d")
p("shard", sh, "of", nsh, "symbols", len(syms))
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for s in syms:
        code = sym2code.get(s)
        if not code: p(s, "no BSE code"); continue
        out = {"C": {}, "S": {}}; have = {"C": [], "S": []}
        for basis, key in (("consolidated", "C"), ("standalone", "S")):
            for q in range(q0, q1):
                try: m = rf.fetch(b, code, s, basis, q)
                except Exception as e: m = None; time.sleep(2)
                if m and m.get("ebitda") is not None and m.get("pat") is not None:
                    out[key][qdate(q)] = {"revenue": m["revenue"] / 10, "ebitda": m["ebitda"] / 10, "pbt": (m["pbt"] or 0) / 10, "pat": m["pat"] / 10}
                    have[key].append(rf.qlabel(q)[:3])
        p(s, code, "C:", "".join(x[0] for x in have["C"]) or "-", "S:", "".join(x[0] for x in have["S"]) or "-", "nC", len(out["C"]), "nS", len(out["S"]))
        k = "C" if out["C"] else "S"
        if out[k]: d = max(out[k]); p("   latest", d, {a: round(v, 2) for a, v in out[k][d].items()})
        if os.path.exists(os.path.join(HIST, s + ".json")): p("   (exists - not overwritten)"); continue
        if out["C"] or out["S"]: json.dump(out, open(os.path.join(HIST, s + ".json"), "w"))
publish()
