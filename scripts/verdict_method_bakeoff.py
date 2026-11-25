"""Verdict methodology bake-off (26 Nov 2026). Four candidate methods on the same results, same price-reaction tests. Calibration only, not a prediction claim.
A = v2 (live rate6)   B = v3.1 absolute pillars + guards   C = peer-relative percentiles (size-segment peers)   D = versus-expectation (surprise vs last quarter's YoY) + same never-event caps
usage: python3 scripts/verdict_method_bakeoff.py"""
import sys, os, gzip, glob, json, collections, statistics as st, datetime as dt, bisect, math
sys.path.insert(0, os.path.dirname(__file__))
import verdict_v3 as v3, verdict_v3_proto as p, quarter_rating as qr
R = os.path.join(os.path.dirname(__file__), "..", "store") + "/"
TIERS = p.TIERS   # Poor..Blockbuster
px = collections.defaultdict(dict); dates = []
for f in sorted(glob.glob(R + "prices/d/202[56]-*_N.csv.gz")):
    d = os.path.basename(f)[:10]; dates.append(d)
    for l in gzip.open(f, "rt"):
        a = l.split(",")
        if len(a) > 8 and a[4] == "EQ":
            try: px[a[2]][d] = float(a[8])
            except Exception: pass
dates = sorted(set(dates))
MONN = {"MAR-2026": 2026 * 4, "JUN-2026": 2026 * 4 + 1}
filed = collections.defaultdict(dict)
for l in open(R + "results_if/numbers.jsonl"):
    r = json.loads(l)
    if r.get("isin") and r.get("filed") and r["to"][3:] in ("MAR-2026", "JUN-2026"):
        try: filed[MONN[r["to"][3:]]].setdefault(r["isin"], dt.datetime.strptime(r["filed"][:11], "%d-%b-%Y").strftime("%Y-%m-%d"))
        except Exception: pass

def mk(n): return {"revenue": n["rev"] * 10, "ebitda": n["ebitda"] * 10, "pat": n["pat"] * 10, "basis": "c"}   # card.py works in Rs million
def A(i, q, f):
    c, y, pv = p.D.get((i, q)), p.D.get((i, q - 4)), p.D.get((i, q - 1))
    if not (c and y and pv): return None
    yp = p.D.get((i, q - 5))
    try: r = qr.rate6(mk(c), mk(pv), mk(y), mk(yp) if yp else None, v11=True, half=False, v12=True, v2=True)
    except Exception: return None
    t = r.get("tier"); return TIERS.index(t) if t in TIERS else None

M31 = [(-3, 0), (0, 60), (2, 80), (5, 100)]     # flat margin = neutral (60) instead of 40
def B(i, q, f):
    old = v3.M; v3.M = M31
    try: t, pil, why = v3.rate(f)
    finally: v3.M = old
    if t not in TIERS: return None
    k = TIERS.index(t)
    c, pv, y = p.D.get((i, q)), p.D.get((i, q - 1)), p.D.get((i, q - 4))
    if c and pv and y and pv["rev"] > 0:
        rq = (c["rev"] / pv["rev"] - 1) * 100
        yp = p.D.get((i, q - 5)); seas = (y["rev"] / yp["rev"] - 1) * 100 if yp and yp["rev"] > 0 else 0
        if rq < -10 and seas > -5: k = min(k, 3)                         # sales QoQ guard: not explained by last year's same seasonal dip
        eq = (c["ebitda"] / pv["ebitda"] - 1) * 100 if pv["ebitda"] > 0 else None
        pq = (c["pat"] / pv["pat"] - 1) * 100 if pv["pat"] > 0 else None
        if k == 5 and rq < 15 and eq is not None and eq < 15 and pq is not None and pq < 15: k = 4   # momentum cap
    return k

PERC = {}
def C(i, q, f):
    if q not in PERC: PERC[q] = p.build(q)[0]
    t = PERC[q].get(i, ("x",))[0]; return TIERS.index(t) if t in TIERS else None

def D(i, q, f):
    pf = p.feats(i, q - 1)
    if not pf: return None
    t, pil, why = v3.rate(f)
    if t not in TIERS: return None
    sp = []
    for k in ("rev_y", "eb_y"):
        if f[k] is not None and pf[k] is not None: sp.append(f[k] - pf[k])
    if not sp or f["mg_y"] is None or pf["mg_y"] is None: return None
    s = 0.7 * (sum(sp) / len(sp)) + 0.3 * (f["mg_y"] - pf["mg_y"]) * 5       # growth acceleration (pp) plus margin-change acceleration (x5 to put pp of margin on the growth scale)
    sc = v3.lin(s, [(-30, 0), (0, 45), (15, 70), (40, 100)])
    k = max(j for j, c_ in enumerate([0, 15, 35, 50, 65, 85]) if sc >= c_)
    cap = TIERS.index(t) if f["pat"] <= 0 or (f["pat_y"] is not None and f["pat_y"] < 0) or f["mg_y"] < -2 else 5     # keep the same hard never-events (loss, profit down YoY, margin down 2+ pts)
    if f["pat"] <= 0: cap = min(cap, 1 if f["pat"] >= f["y_pat"] else 0)
    return min(k, cap)

def ret(i, q, w):
    d = filed[q].get(i)
    if not d or i not in px: return None
    k = bisect.bisect_left(dates, d)
    ix = {"pre": (k - 21, k - 1), "react": (k - 1, k + 2), "post": (k + 2, k + 22)}[w]
    if ix[0] < 0 or ix[1] >= len(dates): return None
    b, e = px[i].get(dates[ix[0]]), px[i].get(dates[ix[1]])
    return (e / b - 1) * 100 if b and e else None

def rank(x):
    s = sorted(range(len(x)), key=lambda j: x[j]); r = [0.0] * len(x); j = 0
    while j < len(s):
        k = j
        while k + 1 < len(s) and x[s[k + 1]] == x[s[j]]: k += 1
        for m in range(j, k + 1): r[s[m]] = (j + k) / 2
        j = k + 1
    return r
def spearman(a, b):
    ra, rb = rank(a), rank(b); ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)); den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else 0

METH = {"A v2 (live)": A, "B v3.1 absolute": B, "C peer percentile": C, "D vs expectation": D}
def run(qs, meths=None, only_common=True):
    meths = meths or METH
    ev = []   # (isin, q, feats)
    for q in qs:
        _, F = p.build(q)
        for i, f in F.items():
            if i in filed[q]: ev.append((i, q, f))
    tiers = {m: {} for m in meths}
    for i, q, f in ev:
        for m in meths:
            fn = METH[m]
            try: tiers[m][(i, q)] = fn(i, q, f)
            except Exception: tiers[m][(i, q)] = None
    keys = [(i, q) for i, q, f in ev]
    if only_common: keys = [k for k in keys if all(tiers[m][k] is not None for m in meths)]
    out = {}
    for w in ("pre", "react", "post"):
        rr = {k: ret(k[0], k[1], w) for k in keys}
        med = {q: st.median([v for (i, qq), v in rr.items() if qq == q and v is not None]) for q in qs}
        ex = {k: v - med[k[1]] for k, v in rr.items() if v is not None}
        out[w] = ex
    return keys, tiers, out

def report(qs, label, meths=None):
    meths = meths or list(METH)
    keys, tiers, out = run(qs, meths)
    print("\n==== %s: %d results rated by all four methods ====" % (label, len(keys)))
    for m in meths:
        mix = collections.Counter(tiers[m][k] for k in keys); n = len(keys)
        print("%-18s mix %%: %s" % (m, " ".join("%s %d" % (TIERS[j][:3], round(mix[j] / n * 100)) for j in range(6))))
    for w, nm in (("react", "reaction (day before filing to 2 days after)"), ("pre", "run-up (20 days before)"), ("post", "drift (20 days after)")):
        print("-- %s" % nm)
        for m in meths:
            ks = [k for k in keys if k in out[w]]
            rho = spearman([tiers[m][k] for k in ks], [out[w][k] for k in ks])
            top = [out[w][k] for k in ks if tiers[m][k] >= 4]; bot = [out[w][k] for k in ks if tiers[m][k] <= 1]
            print("%-18s rank corr %+.3f | top two tiers %+.2f%% (n=%d) vs bottom two %+.2f%% (n=%d) | spread %+.2f" % (m, rho, st.mean(top), len(top), st.mean(bot), len(bot), st.mean(top) - st.mean(bot)))
    return keys, tiers, out

if __name__ == "__main__":
    j = 2026 * 4 + 1
    keys, tiers, out = report([j], "Jun-26 results (only quarter where all four methods can run)")
    report([j - 1], "Mar-26 alone (D needs two quarters of YoY, so A, B, C only)", ["A v2 (live)", "B v3.1 absolute", "C peer percentile"])
    # does the versus-expectation signal add anything on top of B's tier? split each B tier group by D's surprise
    print("\n-- Does 'versus expectation' add on top of B? reaction, B top tiers split by surprise (D tier up vs down relative to B tier)")
    for lab_, cond in (("B top (Excellent+) and D>=Strong", lambda b, d: b >= 4 and d >= 3), ("B top (Excellent+) and D<=Steady", lambda b, d: b >= 4 and d <= 2),
                       ("B mid (Steady/Strong) and D>=Strong", lambda b, d: 2 <= b <= 3 and d >= 3), ("B mid (Steady/Strong) and D<=Weak", lambda b, d: 2 <= b <= 3 and d <= 1),
                       ("B bottom (Poor/Weak) and D>=Steady", lambda b, d: b <= 1 and d >= 2), ("B bottom (Poor/Weak) and D<=Weak", lambda b, d: b <= 1 and d <= 1)):
        sel = [k for k in keys if k in out["react"] and cond(tiers["B v3.1 absolute"][k], tiers["D vs expectation"][k])]
        if sel: print("%-42s n=%4d  reaction %+.2f%%  run-up %+.2f%%  drift %+.2f%%" % (lab_, len(sel), st.mean(out["react"][k] for k in sel), st.mean(out["pre"][k] for k in sel if k in out["pre"]), st.mean(out["post"][k] for k in sel if k in out["post"])))
    # agreement between methods
    print("\n-- Agreement with the live rating (v2): same tier / within one tier")
    for m in ("B v3.1 absolute", "C peer percentile", "D vs expectation"):
        same = sum(tiers[m][k] == tiers["A v2 (live)"][k] for k in keys); near = sum(abs(tiers[m][k] - tiers["A v2 (live)"][k]) <= 1 for k in keys)
        print("%-18s same %d%%  within one %d%%" % (m, same / len(keys) * 100, near / len(keys) * 100))
