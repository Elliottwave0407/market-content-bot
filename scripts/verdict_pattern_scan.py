"""Scan for result patterns whose price reaction differs from their v2.1 tier's average (26 Nov 2026). A candidate rule must hold in BOTH quarters. usage: python3 scripts/verdict_pattern_scan.py"""
import sys, os, math, statistics as st, collections
sys.path.insert(0, os.path.dirname(__file__))
import verdict_method_bakeoff as b, verdict_v3_proto as p, verdict_v21 as v
ASC = v.ASC
def collect(q):
    _, F = p.build(q); rows = []
    for i in F:
        if i not in b.filed[q]: continue
        c, pv, y = p.D.get((i, q)), p.D.get((i, q - 1)), p.D.get((i, q - 4))
        if not (c and pv and y): continue
        yp = p.D.get((i, q - 5))
        try: r = v.rate21(b.mk(c), b.mk(pv), b.mk(y), b.mk(yp) if yp else None)
        except Exception: continue
        if not r.get("tier"): continue
        rx = b.ret(i, q, "react")
        if rx is None: continue
        rows.append({"q": q, "tier": r["tier"], "m": r["m"], "c": c, "pv": pv, "y": y, "rx": rx, "tags": r["tags"]})
    med = st.median(x["rx"] for x in rows)
    for x in rows: x["rx"] -= med
    return rows
rows = collect(2026 * 4) + collect(2026 * 4 + 1)
tm = {t: st.mean(x["rx"] for x in rows if x["tier"] == t) for t in ASC}
for x in rows: x["res"] = x["rx"] - tm[x["tier"]]
g = lambda a, c: None if a is None or c in (None, 0) or c <= 0 else (a / c - 1) * 100
FL = {
 "profit down >10% QoQ (raw)": lambda x: g(x["c"]["pat"], x["pv"]["pat"]) is not None and g(x["c"]["pat"], x["pv"]["pat"]) < -10,
 "EBITDA down >10% QoQ (raw)": lambda x: g(x["c"]["ebitda"], x["pv"]["ebitda"]) is not None and g(x["c"]["ebitda"], x["pv"]["ebitda"]) < -10,
 "sales down QoQ (raw)": lambda x: x["c"]["rev"] < x["pv"]["rev"],
 "margin under 5%": lambda x: x["c"]["rev"] > 0 and x["c"]["ebitda"] / x["c"]["rev"] * 100 < 5,
 "margin over 30%": lambda x: x["c"]["rev"] > 0 and x["c"]["ebitda"] / x["c"]["rev"] * 100 > 30,
 "net margin under 3%": lambda x: x["c"]["rev"] > 0 and x["c"]["pat"] / x["c"]["rev"] * 100 < 3,
 "profit growth under half of EBITDA growth": lambda x: x["m"]["pat_yoy"] is not None and x["m"]["ebitda_yoy"] is not None and x["m"]["ebitda_yoy"] > 20 and x["m"]["pat_yoy"] < x["m"]["ebitda_yoy"] / 2,
 "EBITDA growth under sales growth (deleverage)": lambda x: x["m"]["ebitda_yoy"] is not None and x["m"]["rev_yoy"] is not None and x["m"]["ebitda_yoy"] < x["m"]["rev_yoy"] - 10,
 "profit conversion (PAT/EBITDA) under 30%": lambda x: x["c"]["ebitda"] > 0 and x["c"]["pat"] / x["c"]["ebitda"] < 0.30,
 "profit conversion above 80%": lambda x: x["c"]["ebitda"] > 0 and x["c"]["pat"] / x["c"]["ebitda"] > 0.80,
 "year-ago sales under Rs 50 Cr": lambda x: x["y"]["rev"] < 50,
 "sales over Rs 1,000 Cr": lambda x: x["c"]["rev"] > 1000,
 "sales growth under 10% but profit growth over 40%": lambda x: x["m"]["rev_yoy"] is not None and x["m"]["pat_yoy"] is not None and x["m"]["rev_yoy"] < 10 and x["m"]["pat_yoy"] > 40,
 "profit growth over 3x sales growth (>20% sales)": lambda x: x["m"]["rev_yoy"] is not None and x["m"]["pat_yoy"] is not None and x["m"]["rev_yoy"] > 20 and x["m"]["pat_yoy"] > 3 * x["m"]["rev_yoy"],
 "sales growth accelerating strongly QoQ (>15%)": lambda x: (x["m"].get("rev_qoq") or 0) > 15,
 "margin up >2 pts QoQ": lambda x: x["m"]["margin_qoq_pts"] > 2,
 "margin down >2 pts QoQ": lambda x: x["m"]["margin_qoq_pts"] < -2,
}
print("rows", len(rows), "| tier averages:", {t: round(tm[t], 1) for t in ASC})
def tstat(a):
    return (st.mean(a) / (st.stdev(a) / math.sqrt(len(a)))) if len(a) > 2 and st.stdev(a) > 0 else 0
out = []
for tiers_name, tiers in (("Strong+ (Strong, Excellent, Blockbuster)", ASC[3:]), ("Middle (Steady)", ["Steady"]), ("Weak or Poor", ASC[:2])):
    for name, f in FL.items():
        sel = [x for x in rows if x["tier"] in tiers and f(x)]
        if len(sel) < 20: continue
        a = [x["res"] for x in sel]
        per = [st.mean(x["res"] for x in sel if x["q"] == qq) if sum(1 for x in sel if x["q"] == qq) >= 5 else None for qq in (2026 * 4, 2026 * 4 + 1)]
        out.append((abs(tstat(a)), tiers_name, name, len(sel), st.mean(a), tstat(a), per))
out.sort(reverse=True)
for _, tn, name, n, mean, t, per in out[:22]:
    print("%-40s | %-50s n=%4d residual %+5.2f%% t=%+.1f  by quarter: %s" % (tn[:40], name, n, mean, t, ["n/a" if x is None else "%+.1f" % x for x in per]))
