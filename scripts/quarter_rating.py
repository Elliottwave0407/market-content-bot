"""FinGod quarter rating (draft v1): score 0-100 from EBITDA growth, margin change and revenue growth, then a six-tier label.
Tiers (best->worst): Blockbuster, Excellent, Strong, Steady, Weak, Poor.
Variants (for the design test): V1 as first drafted; V2 'Excellent' minimums moved to the midpoint; V3 softer Blockbuster (EBITDA YoY>=40 plus 3 of the other 4 conditions); V4 owner-approved Blockbuster rule (see rate()).
Pure function of 3 quarters' filed numbers: cur, prev (QoQ base), yago (YoY base). Each is {revenue, ebitda, pat} in Rs Cr."""
TIERS = ["Blockbuster", "Excellent", "Strong", "Steady", "Weak", "Poor"]
CUTS = {"V1": [90, 65, 45, 25, 10], "V2": [90, 74, 60, 38, 15], "V3": [90, 65, 45, 25, 10], "V4": [999, 74, 55, 32, 12]}      # score minimum for tiers 0..4 (Poor below the last)

def band(v, steps):
    """steps: [(min_value, points), ...] descending by min_value"""
    for lo, pts in steps:
        if v >= lo: return pts
    return 0

S_YOY = [(40, 30), (30, 24), (20, 18), (10, 12), (0, 6)]
S_QOQ = [(20, 15), (10, 10), (0, 5)]
S_MYOY = [(4, 20), (2, 14), (0, 8)]
S_MQOQ = [(2, 15), (1, 10), (0, 5)]
S_REV = [(25, 15), (15, 11), (5, 7), (0, 3)]

def g(a, b):
    return None if b is None or a is None or b <= 0 else (a - b) / b * 100

def rate(cur, prev, yago, variant="V1"):
    """returns dict(score, tier, caps, parts, metrics) or dict(tier=None, why=...) when not ratable"""
    for q in (cur, prev, yago):
        if not q or q.get("revenue") in (None, 0) or q.get("ebitda") is None: return {"tier": None, "why": "missing data"}
    if len({q.get("basis") for q in (cur, prev, yago)}) > 1: return {"tier": None, "why": "basis mismatch"}
    m = lambda q: 100 * q["ebitda"] / q["revenue"]
    ey, eq, ry, rq = g(cur["ebitda"], yago["ebitda"]), g(cur["ebitda"], prev["ebitda"]), g(cur["revenue"], yago["revenue"]), g(cur["revenue"], prev["revenue"])
    my, mq = m(cur) - m(yago), m(cur) - m(prev)
    caps, turnaround = [], False
    if ey is None:     # YoY base is zero/negative: growth % is meaningless
        turnaround = cur["ebitda"] > 0
        p_ey = 18 if turnaround else 0
        if turnaround: caps.append(("Excellent", "turnaround from a loss/zero EBITDA base"))
    else: p_ey = band(ey, S_YOY)
    if eq is None: p_eq = 5 if cur["ebitda"] > 0 else 0
    else: p_eq = band(eq, S_QOQ)
    p_my, p_mq = band(my, S_MYOY), band(mq, S_MQOQ)
    p_rv = band(ry, S_REV) if ry is not None else 0
    pat_up = (cur.get("pat") is not None and yago.get("pat") is not None and cur["pat"] > yago["pat"])
    p_pat = 5 if pat_up else 0
    if cur.get("pat") is not None and yago.get("pat") is not None and not pat_up:
        if variant != "V4": caps.append(("Strong", "net profit down YoY"))
        else:   # graded: small dips are tolerated, bigger falls cap harder
            cp, yp = cur["pat"], yago["pat"]
            drop = (yp - cp) / yp * 100 if yp > 0 else 100
            if cp <= 0: caps.append(("Weak", "net loss"))
            elif drop >= 30: caps.append(("Steady", "net profit down 30%+ YoY"))
            elif drop >= 10: caps.append(("Strong", "net profit down 10-30% YoY"))
    if yago["revenue"] < 25 or yago["ebitda"] < 2: caps.append(("Excellent", "small base"))
    score = p_ey + p_eq + p_my + p_mq + p_rv + p_pat
    conds = {"yoy40": ey is not None and ey >= 40, "qoq20": eq is not None and eq >= 20, "mq2": mq >= 2, "my4": my >= 4, "rev20": ry is not None and ry >= 20}
    cuts = CUTS[variant]
    t = next((i for i, c in enumerate(cuts) if score >= c), 5)
    if variant == "V4":     # Blockbuster by rule only: EBITDA YoY>=40, revenue YoY>=20, margin YoY>=0, 2 of {EBITDA QoQ>=20, margin QoQ>=2, margin YoY>=4}, score>=85
        bb = conds["yoy40"] and conds["rev20"] and my >= 0 and sum(conds[k] for k in ("qoq20", "mq2", "my4")) >= 2 and score >= 85
        t = 0 if bb else max(t, 1)
    elif variant == "V3":
        t = 0 if (conds["yoy40"] and sum(conds[k] for k in ("qoq20", "mq2", "my4", "rev20")) >= 3 and score >= 85) else max(t, 1) if t == 0 else t
    else:
        if t == 0 and not all(conds.values()): t = 1
    for tier, _ in caps: t = max(t, TIERS.index(tier))
    return {"tier": TIERS[t], "score": score, "caps": [c[1] for c in caps], "m": {"ebitda_yoy": ey, "ebitda_qoq": eq, "rev_yoy": ry, "rev_qoq": rq, "margin_yoy_pts": round(my, 1), "margin_qoq_pts": round(mq, 1), "margin": round(m(cur), 1), "pat_up": pat_up}}
