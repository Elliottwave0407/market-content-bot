"""FinGod quarter rating (draft v1): score 0-100 from EBITDA growth, margin change and revenue growth, then a six-tier label.
Tiers (best->worst): Blockbuster, Excellent, Strong, Steady, Weak, Poor.
Variants (for the design test): V1 as first drafted; V2 'Excellent' minimums moved to the midpoint; V3 softer Blockbuster (EBITDA YoY>=40 plus 3 of the other 4 conditions); V4 owner-approved Blockbuster rule (see rate()).
Pure function of 3 quarters' filed numbers: cur, prev (QoQ base), yago (YoY base). Each is {revenue, ebitda, pat} in Rs Cr."""
TIERS = ["Blockbuster", "Excellent", "Strong", "Steady", "Weak", "Poor"]
CUTS = {"V1": [90, 65, 45, 25, 10], "V2": [90, 74, 60, 38, 15], "V3": [90, 65, 45, 25, 10], "V4": [999, 76, 60, 35, 16], "V5": [999, 76, 60, 35, 16]}      # score minimum for tiers 0..4 (Poor below the last)

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

def interp(v, anchors):
    """piecewise-linear points: anchors [(value, points), ...] ascending by value; flat beyond both ends. No cliffs: 24.8% revenue growth is worth almost what 25% is."""
    if v <= anchors[0][0]: return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if v <= x1: return y0 + (y1 - y0) * (v - x0) / (x1 - x0)
    return anchors[-1][1]
A_YOY = [(-10, 0), (0, 6), (10, 12), (20, 18), (30, 24), (40, 30)]
A_QOQ = [(-10, 0), (0, 5), (10, 10), (20, 15)]
A_MYOY = [(-2, 0), (0, 8), (2, 14), (4, 20)]
A_MQOQ = [(-1, 0), (0, 5), (1, 10), (2, 15)]
A_REV = [(-5, 0), (0, 3), (5, 7), (15, 11), (25, 15)]
A_MYOY5 = [(-2, 0), (0, 5), (2, 10), (4, 14)]          # V5: margin counts for less (28 of 100 instead of 35), so volume-led all-round growth is not held back by a flat margin
A_MQOQ5 = [(-1, 0), (0, 3), (1, 7), (2, 11)]
A_PAT5 = [(-10, 0), (0, 4), (15, 9), (30, 14)]          # V5: profit growth graded (up to 14) instead of a 5-point yes/no

def g(a, b):
    return None if b is None or a is None or b <= 0 else (a - b) / b * 100

def rate(cur, prev, yago, variant="V1", yprev=None):
    """returns dict(score, tier, caps, parts, metrics) or dict(tier=None, why=...) when not ratable"""
    for q in (cur, prev, yago):
        if not q or q.get("revenue") in (None, 0) or q.get("ebitda") is None: return {"tier": None, "why": "missing data"}
    if len({q.get("basis") for q in (cur, prev, yago)}) > 1: return {"tier": None, "why": "basis mismatch"}
    m = lambda q: 100 * q["ebitda"] / q["revenue"]
    ey, eq, ry, rq = g(cur["ebitda"], yago["ebitda"]), g(cur["ebitda"], prev["ebitda"]), g(cur["revenue"], yago["revenue"]), g(cur["revenue"], prev["revenue"])
    my, mq = m(cur) - m(yago), m(cur) - m(prev)
    my_raw, mq_raw, eq_raw = my, mq, eq
    if variant in ("V4", "V5"):
        # (1) seasonality: remove half of last year's same-quarter QoQ move (QoQ vs same quarter last year correlates ~0.5), when the quarter before year-ago is available
        if not half and yprev and yprev.get("revenue") not in (None, 0) and yprev.get("ebitda") is not None and yprev.get("basis") == cur.get("basis"):
            eq_ly, mq_ly = g(yago["ebitda"], yprev["ebitda"]), m(yago) - m(yprev)
            if eq is not None and eq_ly is not None: eq = eq - 0.5 * max(-40, min(40, eq_ly))      # clipped: one odd year must not swing the result
            mq = mq - 0.5 * max(-6, min(6, mq_ly))
        # (2) headroom: a company already at a high margin has less room to expand, so margin gains are scaled to a 20%-margin starting point (never reduced)
        hp, hy = min(3.0, max(1.0, 80 / (100 - min(m(prev), 95)))), min(3.0, max(1.0, 80 / (100 - min(m(yago), 95))))   # factor capped at 3x
        if mq > 0: mq *= hp
        if my > 0: my *= hy
    caps, turnaround = [], False
    if ey is None:     # YoY base is zero/negative: growth % is meaningless
        turnaround = cur["ebitda"] > 0
        p_ey = 18 if turnaround else 0
        if turnaround: caps.append(("Excellent", "turnaround from a loss/zero EBITDA base"))
    else: p_ey = interp(ey, A_YOY) if variant in ("V4", "V5") else band(ey, S_YOY)
    if eq is None: p_eq = 5 if cur["ebitda"] > 0 else 0
    else: p_eq = interp(eq, A_QOQ) if variant in ("V4", "V5") else band(eq, S_QOQ)
    if variant == "V5": p_my, p_mq = interp(my, A_MYOY5), interp(mq, A_MQOQ5)
    elif variant == "V4": p_my, p_mq = interp(my, A_MYOY), interp(mq, A_MQOQ)
    else: p_my, p_mq = band(my, S_MYOY), band(mq, S_MQOQ)
    p_rv = (interp(ry, A_REV) if variant in ("V4", "V5") else band(ry, S_REV)) if ry is not None else 0
    pat_up = (cur.get("pat") is not None and yago.get("pat") is not None and cur["pat"] > yago["pat"])
    p_pat = 5 if pat_up else 0
    if variant == "V5":
        cp_, yp_ = cur.get("pat"), yago.get("pat")
        if cp_ is None or yp_ is None: p_pat = 0
        elif yp_ > 0: p_pat = interp((cp_ - yp_) / yp_ * 100, A_PAT5)
        else: p_pat = 9 if cp_ > 0 else 0
    if cur.get("pat") is not None and yago.get("pat") is not None and not pat_up:
        if variant not in ("V4", "V5"): caps.append(("Strong", "net profit down YoY"))
        else:   # graded: small dips are tolerated, bigger falls cap harder
            cp, yp = cur["pat"], yago["pat"]
            drop = (yp - cp) / yp * 100 if yp > 0 else 100
            if cp <= 0: caps.append(("Weak", "net loss"))
            elif drop >= 30: caps.append(("Steady", "net profit down 30%+ YoY"))
            elif drop >= 10: caps.append(("Strong", "net profit down 10-30% YoY"))
    if yago["revenue"] < 25 or yago["ebitda"] < 2: caps.append(("Excellent", "small base"))
    score = round(p_ey + p_eq + p_my + p_mq + p_rv + p_pat, 1)
    conds = {"yoy40": ey is not None and ey >= 40, "qoq20": eq is not None and eq >= 20, "mq2": mq >= 2, "my4": my >= 4, "rev20": ry is not None and ry >= 20}
    cuts = CUTS[variant]
    t = next((i for i, c in enumerate(cuts) if score >= c), 5)
    if variant in ("V4", "V5"):     # Blockbuster by rule only: EBITDA YoY>=40, revenue YoY>=20, margin YoY>=0, 2 of {EBITDA QoQ>=20, margin QoQ>=2, margin YoY>=4}, score>=85
        bb = conds["yoy40"] and conds["rev20"] and my >= 0 and sum(conds[k] for k in ("qoq20", "mq2", "my4")) >= 2 and score >= 85
        t = 0 if bb else max(t, 1)
    elif variant == "V3":
        t = 0 if (conds["yoy40"] and sum(conds[k] for k in ("qoq20", "mq2", "my4", "rev20")) >= 3 and score >= 85) else max(t, 1) if t == 0 else t
    else:
        if t == 0 and not all(conds.values()): t = 1
    for tier, _ in caps: t = max(t, TIERS.index(tier))
    return {"tier": TIERS[t], "score": score, "caps": [c[1] for c in caps], "m": {"ebitda_yoy": ey, "ebitda_qoq": eq_raw, "rev_yoy": ry, "rev_qoq": rq, "margin_yoy_pts": round(my_raw, 1), "margin_qoq_pts": round(mq_raw, 1), "adj_margin_yoy": round(my, 1), "adj_margin_qoq": round(mq, 1), "adj_ebitda_qoq": None if eq is None else round(eq, 1), "margin": round(m(cur), 1), "pat_up": pat_up}}


RATING_VERSION = "v2.0"  # Quarterly Verdict. Any later change is a numbered release (v1.2, v2.0) so older cards stay comparable.

# ======================= V6 (= v1.0): fitted to the owner's own ratings of 13 borderline results (Oct 2026) =======================
# Reading order the owner uses: revenue growth first, then profit (PAT), then EBITDA, then margins. Gates and tolerances come from his comments card by card.
W6 = {   # component: (max points, anchors)
    "rev_yoy": [(-5, 0), (0, 3), (10, 10), (20, 16), (30, 22)],
    "rev_qoq": [(-10, 0), (0, 3), (10, 6), (20, 8)],
    "eb_yoy": [(-10, 0), (0, 4), (10, 8), (20, 12), (40, 16)],
    "eb_qoq": [(-10, 0), (0, 2), (10, 4), (20, 6)],
    "pat_yoy": [(-10, 0), (0, 5), (15, 12), (30, 17), (60, 22)],
    "pat_qoq": [(-10, 0), (0, 2), (10, 4), (25, 6)],
    "m_yoy": [(-2, 0), (0, 4), (2, 7), (4, 10)],
    "m_qoq": [(-1, 0), (0, 2), (1, 4), (2, 6)],
}
CUTS6 = [999, 70, 48, 36, 20]
BB_SCORE6 = 80

# Banks and insurers (records carry kind = bank / life / general, see fin_data._special). Margin = pre-provision profit / net total income for banks (1 - cost-to-income);
# shareholders' PBT / net premium for insurers. Margins of such businesses move in much smaller steps, so margin changes are scaled up and a tiny dip is tolerated.
KIND_PARAMS = {"bank": {"mscale": 1.5, "mtol": 1.0}, "life": {"mscale": 4.0, "mtol": 0.3}, "general": {"mscale": 1.0, "mtol": 1.0}}

V2_SC = {"rev_yoy": 22 / 22, "rev_qoq": 7 / 8, "pat_yoy": 23 / 22, "pat_qoq": 1.0, "m_yoy": 14 / 10, "m_qoq": 8 / 6, "eb_yoy": 11 / 16, "eb_qoq": 5 / 6}      # points out of 96: revenue 22+7=29, PAT 23+6=29, operating side 38 = margin % 14+8 and EBITDA growth 11+5

def rate6(cur, prev, yago, yprev=None, cuts=None, bb_score=None, v11=False, older=None, half=False, v12=False, v2=False):
    """half=True: half-yearly results (SME). prev = the preceding half-year, yago = the same half last year; the sequential (HoH) changes cover six months, so they are halved to a per-quarter equivalent before scoring, and no seasonality adjustment is applied. v1.0 when v11=False (frozen). v11=True adds the size-aware / noise-aware rules (see RATING_NOTES_V11). older=(yago2, yprev2): the same two quarters one year earlier, for the two-year seasonality check."""
    cuts, bb_score = cuts or CUTS6, bb_score if bb_score is not None else BB_SCORE6
    for q in (cur, prev, yago):
        if not q or q.get("revenue") in (None, 0) or q.get("ebitda") is None: return {"tier": None, "why": "missing data"}
    if len({q.get("basis") for q in (cur, prev, yago)}) > 1: return {"tier": None, "why": "basis mismatch"}
    m = lambda q: 100 * q["ebitda"] / q["revenue"]
    ey, eq = g(cur["ebitda"], yago["ebitda"]), g(cur["ebitda"], prev["ebitda"])
    ry, rq = g(cur["revenue"], yago["revenue"]), g(cur["revenue"], prev["revenue"])
    cp, pp, yp = cur.get("pat"), prev.get("pat"), yago.get("pat")
    pyo = None if cp is None or yp is None or yp <= 0 else (cp - yp) / yp * 100
    pqo = None if cp is None or pp is None or pp <= 0 else (cp - pp) / pp * 100
    my, mq = m(cur) - m(yago), m(cur) - m(prev)
    raw = dict(rev_yoy=ry, rev_qoq=rq, eb_yoy=ey, eb_qoq=eq, pat_yoy=pyo, pat_qoq=pqo, m_yoy=my, m_qoq=mq, margin=m(cur))
    # seasonality: remove part of last year's same-quarter QoQ move (clipped), when the quarter before year-ago is known
    sf = lambda x, c: max(-c, min(c, x))
    seas = False
    if yprev and yprev.get("revenue") not in (None, 0) and yprev.get("ebitda") is not None and yprev.get("basis") == cur.get("basis"):
        rq_ly, eq_ly, mq_ly = g(yago["revenue"], yprev["revenue"]), g(yago["ebitda"], yprev["ebitda"]), m(yago) - m(yprev)
        seas = True
        ins = cur.get("kind") in ("life", "general")      # insurers: premium is strongly seasonal, remove the whole of last year's same-quarter move
        w_r = w_e = w_m = 0.5
        rq_ly2 = eq_ly2 = mq_ly2 = None
        if v11 and older and older[0] and older[1] and older[0].get("revenue") not in (None, 0) and older[1].get("revenue") not in (None, 0) and older[0].get("ebitda") is not None and older[1].get("ebitda") is not None:
            rq_ly2, eq_ly2, mq_ly2 = g(older[0]["revenue"], older[1]["revenue"]), g(older[0]["ebitda"], older[1]["ebitda"]), m(older[0]) - m(older[1])
        def adj(cur_v, ly, ly2, clip, floor):
            if cur_v is None or ly is None: return cur_v
            if v11 and ly2 is not None and (ly > 0) == (ly2 > 0) and min(abs(ly), abs(ly2)) >= floor:      # same-direction move in both past years = a real seasonal pattern: correct harder
                return cur_v - (1.0 if ins else 0.8) * sf((ly + ly2) / 2, clip)
            return cur_v - (1.0 if ins else 0.5) * sf(ly, clip)
        rq = adj(rq, rq_ly, rq_ly2, 30, 5); eq = adj(eq, eq_ly, eq_ly2, 40, 5); mq = adj(mq, mq_ly, mq_ly2, 6, 1)
    if half:
        rq, eq, mq = (None if x is None else x * 0.5 for x in (rq, eq, mq)); pqo = None if pqo is None else pqo * 0.5
    kp = KIND_PARAMS.get(cur.get("kind"), {})
    if kp: my, mq = my * kp["mscale"], mq * kp["mscale"]
    # margin level: a small dip is tolerated when the margin is already high; gains are scaled to the room left (capped 3x)
    tol = min(2.5, 1.0 + max(0.0, m(cur) - 20) * 0.05) if m(cur) >= 20 else 0.0
    if my < 0: my = min(0.0, my + tol)
    if mq < 0: mq = min(0.0, mq + tol)
    if mq > 0: mq *= min(3.0, max(1.0, 80 / (100 - min(m(prev), 95))))
    if my > 0: my *= min(3.0, max(1.0, 80 / (100 - min(m(yago), 95))))
    caps = []
    P = {}
    P["rev_yoy"] = interp(ry, W6["rev_yoy"]) if ry is not None else 0
    P["rev_qoq"] = interp(rq, W6["rev_qoq"]) if rq is not None else 0
    if ey is None:
        P["eb_yoy"] = 10 if cur["ebitda"] > 0 else 0
        if cur["ebitda"] > 0: caps.append(("Excellent", "turnaround from a loss/zero EBITDA base"))
    else: P["eb_yoy"] = interp(ey, W6["eb_yoy"])
    P["eb_qoq"] = interp(eq, W6["eb_qoq"]) if eq is not None else (4 if cur["ebitda"] > 0 else 0)
    if cp is None or yp is None: P["pat_yoy"] = 0
    elif yp > 0: P["pat_yoy"] = interp(pyo, W6["pat_yoy"])
    else: P["pat_yoy"] = 12 if cp > 0 else 0
    P["pat_qoq"] = interp(pqo, W6["pat_qoq"]) if pqo is not None else (4 if cp is not None and cp > 0 else 0)
    P["m_yoy"], P["m_qoq"] = interp(my, W6["m_yoy"]), interp(mq, W6["m_qoq"])
    if v11:
        # (a) abnormal quarter-ago base: after an exceptional loss quarter, QoQ comparisons mean nothing, so they score neutral
        base_bad = prev["ebitda"] <= 0 or m(prev) < -20 or (pp is not None and pp < 0 and abs(pp) > 0.2 * prev["revenue"])
        if base_bad: P["eb_qoq"], P["m_qoq"], P["pat_qoq"] = 2, 2, 2
        # (b) tiny profit base: PAT growth % is noise when last year's PAT is under Rs 1 Cr or under 1.5% of revenue
        pat_noise = yp is not None and 0 < yp < max(1.0, 0.015 * yago["revenue"])
        if pat_noise: P["pat_yoy"] = 7
        pat_reliable = not pat_noise
    if cur.get("kind") in ("life", "general") and not seas: P["rev_qoq"] = 3      # insurers' premium is strongly seasonal (e.g. life: Mar high, Jun low, Sep rebound): without the seasonal history a QoQ jump says nothing
    if v2:      # v2.0: revenue, margins and PAT carry equal weight (32 of 96 each). Margins pillar = margin level change (YoY 14, QoQ 8) + EBITDA growth (YoY 7, QoQ 3)
        P = {k: v * V2_SC[k] for k, v in P.items()}
    score = round(sum(P.values()) * 100 / 96, 1)
    pat_reliable = locals().get('pat_reliable', True)
    # gates (from the owner's calls)
    if cp is not None and cp <= 0: caps.append(("Weak", "net loss"))
    elif pyo is not None and pyo <= -30: caps.append(("Weak", "net profit down 30%+ YoY"))
    elif pyo is not None and pyo <= -5: caps.append(("Steady", "net profit down YoY"))
    elif pyo is not None and pyo < 0: caps.append(("Strong", "net profit slightly down YoY"))
    rq_raw = raw["rev_qoq"]
    if rq is not None and rq < -5: caps.append(("Steady", "revenue fell more than 5% QoQ (seasonally adjusted)"))
    if rq_raw is not None and rq_raw < 0 and pqo is not None and pqo < 0 and pyo is not None and pyo < 10: caps.append(("Weak", "revenue and profit both fell QoQ with profit barely up YoY"))
    if ry is not None and ry < 15:        # revenue is the gate: weak top-line growth needs exceptional profit growth to rise
        grows = rq_raw is not None and rq_raw >= 0      # the profit exception only applies when the top line is not shrinking QoQ
        if pyo is not None and pyo >= 50 and grows and pat_reliable: pass
        elif pyo is not None and pyo >= 30 and grows and pat_reliable: caps.append(("Strong", "revenue growth under 15% YoY"))
        else: caps.append(("Steady", "revenue growth under 15% YoY without 30%+ profit growth"))
    if raw["m_qoq"] < -kp.get("mtol", 0): caps.append(("Strong", "margin fell QoQ"))
    if v2 and raw["m_qoq"] < -kp.get("mtol", 0) and raw["m_yoy"] <= 0.05: caps.append(("Steady", "margin fell QoQ and is not up YoY"))      # margins drive the price: a falling margin that is not above last year's caps the verdict at Steady
    if v11 and not (prev["ebitda"] <= 0 or m(prev) < -20):
        if (eq is not None and eq <= -30) or (pqo is not None and pqo <= -30 and (pp or 0) > 0): caps.append(("Steady", "EBITDA or profit fell 30%+ QoQ"))     # an Excellent quarter should not show falling margins
    if (yago["revenue"] < 25) or (yago["ebitda"] < 2): caps.append(("Excellent", "small base"))
    t = next((i for i, c in enumerate(cuts) if score >= c), 5)
    conds = {"yoy40": ey is not None and ey >= 40, "rev20": ry is not None and ry >= 20, "qoq20": eq is not None and eq >= 20, "mq2": mq >= 2, "my4": my >= 4}
    pathA = conds["yoy40"] and conds["rev20"] and my >= 0 and sum(conds[k] for k in ("qoq20", "mq2", "my4")) >= 2 and score >= bb_score
    pathB = all(v is not None and v >= 50 for v in (ry, ey, pyo)) and rq is not None and rq >= 0 and (not v12 or raw["m_yoy"] >= -3)      # v1.2: margin may not fall more than 3 pts YoY. explosive all-round growth (e.g. revenue, EBITDA and PAT all more than +50% YoY), margin not required
    t = 0 if (pathA or pathB) else max(t, 1)
    for tier, why in caps:
        if pathB and why.startswith("margin fell QoQ"): continue      # explosive growth is judged on growth, not on a flat margin
        t = max(t, TIERS.index(tier))
    return {"tier": TIERS[t], "score": score, "caps": [c[1] for c in caps], "parts": {k: round(v, 1) for k, v in P.items()},
            "m": {"ebitda_yoy": ey, "ebitda_qoq": eq, "rev_yoy": ry, "rev_qoq": rq, "pat_yoy": pyo, "pat_qoq": pqo, "margin_yoy_pts": round(raw["m_yoy"], 1), "margin_qoq_pts": round(raw["m_qoq"], 1), "margin": round(m(cur), 1)}}


# ======================= Finance companies (draft v0, Oct 2026) =======================
LENDERS = set("HDBFS HUDCO IREDA LICHSGFIN M&MFIN MANAPPURAM PNBHOUSING POONAWALLA SBICARD".split())          # lenders: net interest income (revenue - finance costs) stands in for EBITDA
CAPMARKET = set("360ONE ABSLAMC ANANDRATHI ANGELONE NUVAMA".split())                                         # brokers/AMCs/wealth: the normal operating-profit model fits
def to_lender(m):
    if not m or m.get("revenue") in (None, 0) or m.get("fin") is None: return None
    return dict(m, ebitda=round(m["revenue"] - m["fin"], 2))
def rate_fin(kind, cur, prev, yago, yprev=None, **kw):
    """kind: 'lender' or 'capmarket'. Same rulebook as rate6, but a lender's 'EBITDA' is its net interest income, so its 'margin' is the spread kept after funding cost."""
    if kind == "lender":
        cur, prev, yago, yprev = to_lender(cur), to_lender(prev), to_lender(yago), to_lender(yprev)
        if not (cur and prev and yago): return {"tier": None, "why": "missing finance cost"}
    return rate6(cur, prev, yago, yprev, **kw)
