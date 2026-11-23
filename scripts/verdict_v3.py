"""Quarterly Verdict v3 (prototype, 23 Nov 2026): fixed absolute rules on the company's own numbers. No peers, no AI.
Pillars (0-100, piecewise-linear on published anchors): Growth, Profitability, Profit quality. Score = 0.5*weakest + 0.5*average.
Tier cut-offs fixed; hard ceilings only pull a tier down. Thin data -> Provisional."""
import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
import verdict_v3_proto as p
TIERS = p.TIERS
CUTS = [0, 10, 28, 44, 60, 78]   # Poor, Weak, Steady, Strong, Excellent, Blockbuster (score)
def lin(x, pts):
    if x <= pts[0][0]: return pts[0][1]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if x <= c: return b + (d - b) * (x - a) / (c - a)
    return pts[-1][1]
G = [(-30, 0), (0, 25), (10, 42), (20, 60), (35, 80), (60, 100)]
M = [(-3, 0), (0, 40), (2, 65), (5, 100)]
CV = [(30, 0), (60, 50), (90, 100)]
def rate(f):
    if f is None: return "Provisional", {}, "history missing"
    if f["y_rev"] < 5 or (abs(f["y_pat"]) < 0.3 and f["pat"] < 1): return "Provisional", {}, "tiny base"
    gr = [lin(f["rev_y"], G)] if f["rev_y"] is not None else []
    if f["eb_y"] is not None: gr.append(lin(f["eb_y"], G))
    if not gr: return "Provisional", {}, "no growth base"
    growth = sum(gr) / len(gr)
    prof = lin(f["mg_y"], M) * 0.8 + (min(f["mg"], 25) / 25 * 100) * 0.2
    q = [lin(f["pat_y"], G)] if f["pat_y"] is not None else []
    if f.get("pm_y") is not None: q.append(lin(f["pm_y"], M))
    if not q: return "Provisional", {}, "no profit base"
    qual = sum(q) / len(q)
    if f["oi_share"] is not None and f["oi_share"] > 40: qual *= 0.8
    pil = {"growth": growth, "profit": prof, "quality": qual}
    sc = max(0, 0.5 * min(pil.values()) + 0.5 * sum(pil.values()) / 3)
    t = max(j for j, c in enumerate(CUTS) if sc >= c)
    why = None
    def cap(n, r):
        nonlocal t, why
        if t > n: t, why = n, r
    if f["pat"] <= 0: cap(0 if f["pat"] < f["y_pat"] else 1, "net loss")
    if f["pat_y"] is None and f["y_pat"] <= 0: cap(4, "turnaround from a loss base")
    if f["pat_y"] is not None and f["pat_y"] < 0: cap(2, "profit down YoY")
    if f["rev_y"] is not None and f["rev_y"] < 0: cap(2, "revenue down YoY")
    elif f["rev_y"] is not None and f["rev_y"] < 10: cap(3, "revenue growth under 10%")
    elif f["rev_y"] is not None and f["rev_y"] < 20: cap(4, "revenue growth under 20%")
    if f["mg_y"] < -2: cap(2, "margin down over 2 pts YoY")
    elif f["mg_y"] < -0.5: cap(3, "margin down YoY")
    elif f["mg_y"] < 0: cap(4, "margin slightly down YoY")
    if f["mg_q"] is not None and f["mg_q"] < -1: cap(4, "margin down over 1 pt QoQ")
    if f["pat_y"] is not None and f["pat_y"] < 25: cap(3, "profit growth under 25%")
    if t == 5 and min(pil.values()) < 55: t, why = 4, "one pillar weak"
    return TIERS[t], {k: round(x) for k, x in pil.items()}, why
if __name__ == "__main__":
    for q in (2026 * 4 + 1, 2026 * 4):
        _, F = p.build(q); o = {i: rate(f) for i, f in F.items()}
        c = collections.Counter(v[0] for v in o.values()); n = sum(c[t] for t in TIERS)
        print(q // 4, q % 4, "mix%", {t: round(c[t] / n * 100) for t in TIERS}, "Prov", c["Provisional"])
        bad = sum(1 for i, (t, _, _) in o.items() if (t == "Blockbuster" and (F[i]["mg_y"] < 0 or (F[i]["mg_q"] or 0) < -1 or (F[i]["pat_y"] if F[i]["pat_y"] is not None else 99) < 25)) or (t in ("Excellent", "Blockbuster") and (F[i]["pat"] <= 0 or (F[i]["pat_y"] or 0) < 0)))
        print("  never-event violations", bad)
        import random; rng = random.Random(1); _, F2 = p.build(q, 0.05, rng); ch = jp = tot = 0
        for i, (t, _, _) in o.items():
            t2 = rate(F2[i])[0]
            if t in TIERS and t2 in TIERS: tot += 1; d = abs(TIERS.index(t) - TIERS.index(t2)); ch += d > 0; jp += d > 1
        print("  stability: changed %.1f pct, two-level jumps %.2f pct" % (ch / tot * 100, jp / tot * 100))
