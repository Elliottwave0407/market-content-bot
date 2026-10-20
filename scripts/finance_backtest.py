"""Standalone debug: rate finance companies (lenders via net interest income; capital-market firms via the normal model) on cached history."""
import os, sys, json, glob
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import quarter_rating as qr
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def shift(d, months):
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12); m += 1
    return datetime(y, m, 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30 if m != 2 else 28)
out = []
for f in sorted(glob.glob(os.path.join(ROOT, "companydata", "_hist", "*.json"))):
    d = json.load(open(f)); sym = d["symbol"]
    kind = "lender" if sym in qr.LENDERS else "capmarket" if sym in qr.CAPMARKET else None
    if not kind: continue
    for b in ("C", "S"): d[b] = {datetime.strptime(k, "%Y-%m-%d"): dict(v, basis=b) for k, v in d[b].items()}
    for q in sorted(set(d["C"]) | set(d["S"])):
        for b in ("C", "S"):
            cur, pr, ya = d[b].get(q), d[b].get(shift(q, 3)), d[b].get(shift(q, 12))
            if cur and pr and ya: break
        else: continue
        r = qr.rate_fin(kind, cur, pr, ya, d[b].get(shift(q, 15)))
        if r.get("tier"): out.append(dict(symbol=sym, kind=kind, q=q.strftime("%b-%y"), tier=r["tier"], score=r["score"], caps=r["caps"], m=r["m"]))
for kind in ("lender", "capmarket"):
    o = [r for r in out if r["kind"] == kind]; c = Counter(r["tier"] for r in o); n = len(o)
    print(kind, n, "quarters,", len(set(r["symbol"] for r in o)), "companies:", " | ".join(f"{t} {c.get(t,0)} ({100*c.get(t,0)/max(n,1):.0f}%)" for t in qr.TIERS))
json.dump(out, open(os.path.join(ROOT, "companydata", "_readiness", "finance_test.json"), "w"))
f = lambda x: "n/a" if x is None else f"{x:+.0f}%"
for r in [x for x in out if x["q"] in ("Jun-26", "Sep-26")]:
    m = r["m"]; print(f"{r['symbol']:11}{r['q']} {r['tier']:11}{r['score']:5.0f} | rev {f(m['rev_yoy'])}/{f(m['rev_qoq'])} core {f(m['ebitda_yoy'])}/{f(m['ebitda_qoq'])} PAT {f(m['pat_yoy'])}/{f(m['pat_qoq'])} margin {m['margin']}")
