"""Design test (no AI, no price data): score the last 4 quarters of each screened company under rating variants V1/V2/V3 and report tier distributions + borderline examples.
Env: SYMBOLS (optional comma list), MAXN."""
import os, sys, json, time
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd, quarter_rating as qr
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
syms = [x.strip().upper() for x in os.environ.get("SYMBOLS", "").split(",") if x.strip()]
if not syms:
    syms = [r["symbol"] for r in json.load(open(os.path.join(ROOT, "companydata", "_readiness", "screen.json")))["rows"] if r.get("readiness", -1) >= 0]
syms = syms[: int(os.environ.get("MAXN", "200"))]
ME = lambda l: datetime.strptime("01-" + l, "%d-%b-%y")
mon = lambda l: ME(l).year * 12 + ME(l).month
out, t0 = [], time.time()
for i, sym in enumerate(syms):
    try:
        rows = fd.merged(nse.sess(), sym)
    except Exception as e:
        p("fail", sym, repr(e)[:60]); continue
    for j in range(len(rows) - 1, max(len(rows) - 5, 3), -1):
        if j < 4: break
        (lc, c), (lp, pr), (ly, ya) = rows[j], rows[j - 1], rows[j - 4]
        if mon(lc) - mon(lp) != 3 or mon(lc) - mon(ly) != 12: continue
        rec = {"symbol": sym, "q": lc, "latest": j == len(rows) - 1}
        for v in ("V1", "V2", "V3"):
            r = qr.rate(c, pr, ya, v); rec[v] = {k: r.get(k) for k in ("tier", "score", "caps", "why")}
            if v == "V1": rec["m"] = r.get("m")
        out.append(rec)
    if (i + 1) % 10 == 0: p(f"  {i+1}/{len(syms)} done, {time.time()-t0:.0f}s")
os.makedirs(os.path.join(ROOT, "companydata", "_readiness"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "companydata", "_readiness", "rating_test.json"), "w"))
ok = [r for r in out if r["V1"]["tier"]]
p(f"scored {len(ok)} of {len(out)} company-quarters; skipped: {dict(Counter(r['V1'].get('why') for r in out if not r['V1']['tier']))}")
for v in ("V1", "V2", "V3"):
    c = Counter(r[v]["tier"] for r in ok); n = len(ok)
    p(v, " | ".join(f"{t} {c.get(t,0)} ({100*c.get(t,0)/n:.0f}%)" for t in qr.TIERS))
lat = [r for r in ok if r["latest"]]
for v in ("V1", "V2", "V3"):
    c = Counter(r[v]["tier"] for r in lat); n = len(lat)
    p(v, "latest quarter only:", " | ".join(f"{t} {c.get(t,0)}" for t in qr.TIERS), f"(n={n})")
capc = Counter(cp for r in ok for cp in (r["V1"]["caps"] or []))
p("caps applied (V1):", dict(capc))
def line(r):
    m = r["m"]; f = lambda x: "n/a" if x is None else f"{x:+.0f}%"
    return f"{r['symbol']} {r['q']}: score {r['V1']['score']} | EBITDA {f(m['ebitda_yoy'])} YoY {f(m['ebitda_qoq'])} QoQ | margin {m['margin']}% ({m['margin_yoy_pts']:+} YoY, {m['margin_qoq_pts']:+} QoQ) | rev {f(m['rev_yoy'])} YoY | V1 {r['V1']['tier']} V2 {r['V2']['tier']} V3 {r['V3']['tier']}"
p("--- Blockbuster under V1:")
for r in sorted([r for r in ok if r["V1"]["tier"] == "Blockbuster"], key=lambda r: -r["V1"]["score"])[:8]: p(line(r))
p("--- borderline: V1 score 78-89 (top of Excellent):")
for r in sorted([r for r in ok if r["V1"]["tier"] == "Excellent" and r["V1"]["score"] >= 78], key=lambda r: -r["V1"]["score"])[:10]: p(line(r))
p("--- bottom: Poor under V1:")
for r in sorted([r for r in ok if r["V1"]["tier"] == "Poor"], key=lambda r: r["V1"]["score"])[:5]: p(line(r))
publish()
