"""v2.1 candidate rules tested against v2 on price reaction (26 Nov 2026). Calibration on Mar-26 and Jun-26 results; nothing here is live.
Rules tested on top of v2 (rate6): (R1) Blockbuster Route B needs margin not falling (YoY >= -1 pt, QoQ >= -2 pt); (R2) momentum: when YoY is strong but sequential change is flat on all three of sales, EBITDA, profit, step the tier down.
usage: python3 scripts/verdict_v21_test.py"""
import sys, os, statistics as st
sys.path.insert(0, os.path.dirname(__file__))
import verdict_method_bakeoff as b, verdict_v3_proto as p, quarter_rating as qr
TIERS = p.TIERS      # ascending: Poor .. Blockbuster

def v2(i, q, older=True):
    c, y, pv = p.D.get((i, q)), p.D.get((i, q - 4)), p.D.get((i, q - 1))
    if not (c and y and pv): return None
    yp = p.D.get((i, q - 5))
    try: return qr.rate6(b.mk(c), b.mk(pv), b.mk(y), b.mk(yp) if yp else None, v11=True, half=False, v12=True, v2=True)
    except Exception: return None

def flat(m, x):
    v = [m.get("rev_qoq"), m.get("ebitda_qoq"), m.get("pat_qoq")]
    return all(a is not None and a < x for a in v)

def v21(r, R1=True, X=15, drop=1, floor_tier=2):
    k = TIERS.index(r["tier"]); m = r["m"]
    if R1 and k == 5:
        pathA_like = m["ebitda_yoy"] is not None and m["ebitda_yoy"] >= 40 and m["rev_yoy"] is not None and m["rev_yoy"] >= 20
        if not pathA_like and (m["margin_yoy_pts"] < -1 or m["margin_qoq_pts"] < -2): k = 4          # Route B (explosive growth) stays Blockbuster only when margin is not falling
    if X and k >= 4 and m["ebitda_yoy"] is not None and flat(m, X): k = max(floor_tier, k - drop)
    return k

def run(q):
    _, F = p.build(q)
    ev = [(i, f) for i, f in F.items() if i in b.filed[q]]
    base = {}
    for i, f in ev:
        r = v2(i, q)
        if r and r.get("tier") in TIERS: base[i] = r
    out = {}
    for w in ("pre", "react", "post"):
        rr = {i: b.ret(i, q, w) for i in base}
        med = st.median([v for v in rr.values() if v is not None])
        out[w] = {i: v - med for i, v in rr.items() if v is not None}
    return base, out

def rc(tf, base, out, w="react"):
    ks = [i for i in base if i in out[w]]
    return b.spearman([tf(i) for i in ks], [out[w][i] for i in ks])

if __name__ == "__main__":
    for q, lab in ((2026 * 4, "Mar-26"), (2026 * 4 + 1, "Jun-26")):
        base, out = run(q)
        print("\n==== %s: %d results ====" % (lab, len(base)))
        print("v2 (live): rank corr react %.3f  run-up %.3f  drift %.3f" % (rc(lambda i: TIERS.index(base[i]["tier"]), base, out), rc(lambda i: TIERS.index(base[i]["tier"]), base, out, "pre"), rc(lambda i: TIERS.index(base[i]["tier"]), base, out, "post")))
        bb = [i for i in base if base[i]["tier"] == "Blockbuster"]
        bad = [i for i in bb if base[i]["m"]["margin_yoy_pts"] < 0 or base[i]["m"]["margin_qoq_pts"] < -1 or (base[i]["m"]["pat_yoy"] or 99) < 25]
        print("v2 Blockbusters %d; with margin down YoY or QoQ >1 pt or profit growth under 25%%: %d (avg reaction %+.2f%% vs %+.2f%% for the rest)" % (len(bb), len(bad), st.mean(out["react"][i] for i in bad if i in out["react"]) if bad else 0, st.mean(out["react"][i] for i in bb if i not in bad and i in out["react"])))
        print("-- flat-momentum split of v2 top tiers (flat = sales, EBITDA, profit QoQ all under X%, seasonally adjusted)")
        for X in (5, 10, 15, 20):
            for t in ("Blockbuster", "Excellent"):
                fl = [i for i in base if base[i]["tier"] == t and flat(base[i]["m"], X) and i in out["react"]]
                mv = [i for i in base if base[i]["tier"] == t and not flat(base[i]["m"], X) and i in out["react"]]
                if fl and mv: print("X=%2d %-11s flat n=%3d reaction %+.2f%% | moving n=%3d reaction %+.2f%%" % (X, t, len(fl), st.mean(out["react"][i] for i in fl), len(mv), st.mean(out["react"][i] for i in mv)))
        print("-- reference: average reaction by v2 tier")
        for t in TIERS:
            g_ = [out["react"][i] for i in base if base[i]["tier"] == t and i in out["react"]]
            print("   %-11s n=%4d %+.2f%%" % (t, len(g_), st.mean(g_)))
        print("-- variants")
        for lab2, kw in (("R1 only", dict(R1=True, X=0)), ("R2 only X=10", dict(R1=False, X=10)), ("R2 only X=15", dict(R1=False, X=15)), ("R2 only X=20", dict(R1=False, X=20)), ("R1 + R2 X=15", dict(R1=True, X=15)), ("R1 + R2 X=15 Bb only", dict(R1=True, X=15, floor_tier=4))):
            tf = lambda i, kw=kw: v21(base[i], **kw)
            ch = sum(tf(i) != TIERS.index(base[i]["tier"]) for i in base)
            print("%-22s changed %3d (%.1f%%) | rank corr react %.3f run-up %.3f drift %.3f" % (lab2, ch, ch / len(base) * 100, rc(tf, base, out), rc(tf, base, out, "pre"), rc(tf, base, out, "post")))
