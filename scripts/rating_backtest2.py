"""Like-for-like backtest on cached quarter history (companydata/_hist). For each quarter with prev (3m) and year-ago (12m) on the SAME basis (consolidated preferred), rate under V2 and V4.
Env: LATEST_ONLY=1 to score only each company's newest quarter."""
import os, sys, json, glob
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import quarter_rating as qr
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def shift(d, months):
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12); m += 1
    nm = (31 if m in (1, 3, 5, 7, 8, 10, 12) else 30 if m != 2 else 28)
    return datetime(y, m, nm)
out, nofile = [], 0
for f in sorted(glob.glob(os.path.join(ROOT, "companydata", "_hist", "*.json"))):
    d = json.load(open(f)); sym = d["symbol"]
    for b in ("C", "S"):
        d[b] = {datetime.strptime(k, "%Y-%m-%d"): dict(v, basis=b) for k, v in d[b].items()}
    qs = sorted(set(d["C"]) | set(d["S"]))
    newest = qs[-1] if qs else None
    for q in qs:
        for b in ("C", "S"):
            cur, pr, ya = d[b].get(q), d[b].get(shift(q, 3)), d[b].get(shift(q, 12))
            if cur and pr and ya: break
        else: continue
        rec = {"symbol": sym, "q": q.strftime("%b-%y"), "basis": b, "latest": q == newest}
        for v in ("V2", "V4"):
            r = qr.rate(cur, pr, ya, v); rec[v] = {k: r.get(k) for k in ("tier", "score", "caps", "why")}
            if v == "V2": rec["m"] = r.get("m")
        out.append(rec)
json.dump(out, open(os.path.join(ROOT, "companydata", "_readiness", "rating_test2.json"), "w"))
ok = [r for r in out if r["V2"]["tier"]]
p(f"{len(set(r['symbol'] for r in out))} companies, {len(ok)} like-for-like company-quarters; basis used: {dict(Counter(r['basis'] for r in ok))}")
for v in ("V2", "V4"):
    c = Counter(r[v]["tier"] for r in ok); n = len(ok)
    p(v, " | ".join(f"{t} {c.get(t,0)} ({100*c.get(t,0)/n:.0f}%)" for t in qr.TIERS))
lat = [r for r in ok if r["latest"]]
for v in ("V2", "V4"):
    c = Counter(r[v]["tier"] for r in lat); n = len(lat)
    p(v, f"newest quarter only (n={n}):", " | ".join(f"{t} {c.get(t,0)}" for t in qr.TIERS))
p("caps applied:", dict(Counter(cp for r in ok for cp in (r["V4"]["caps"] or []))))
by = {}
for r in ok: by.setdefault(r["q"], Counter())[r["V4"]["tier"]] += 1
p("V4 by quarter (shows seasonality/market mood):")
for q in sorted(by, key=lambda s: datetime.strptime("01-" + s, "%d-%b-%y")): p("  ", q, sum(by[q].values()), dict(by[q]))
def line(r):
    m = r["m"]; f = lambda x: "n/a" if x is None else f"{x:+.0f}%"
    return f"{r['symbol']} {r['q']} score {r['V4']['score']} | EBITDA {f(m['ebitda_yoy'])} YoY {f(m['ebitda_qoq'])} QoQ | margin {m['margin']}% ({m['margin_yoy_pts']:+} YoY, {m['margin_qoq_pts']:+} QoQ) | rev {f(m['rev_yoy'])} YoY | V2 {r['V2']['tier']} V4 {r['V4']['tier']}"
p("--- V4 Blockbusters (top 12 by score):")
for r in sorted([r for r in ok if r["V4"]["tier"] == "Blockbuster"], key=lambda r: -r["V4"]["score"])[:12]: p(line(r))
p("--- near-misses: V4 Excellent with score>=85:")
for r in sorted([r for r in ok if r["V4"]["tier"] == "Excellent" and r["V4"]["score"] >= 85], key=lambda r: -r["V4"]["score"])[:10]: p(line(r))
publish()
