"""Verdict card PROTOTYPE v3 layout, rating = Verdict v2.1 (five-column table + 5-quarter trend chart + how the verdict is built (v2 points) + tags + history). Not wired into production.
usage: python3 scripts/verdict_card_v2.py [SYMBOL] [OUT_DIR]"""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.patches import FancyBboxPatch
import theme as T, verdict_v21 as v21

SYM = sys.argv[1] if len(sys.argv) > 1 else "ACMESOLAR"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
H = json.load(open(os.path.join(os.path.dirname(__file__), "..", "companydata", "_hist", SYM + ".json")))
B = "C" if H["C"] else "S"
NAME = H.get("name")
if not NAME:
    try: NAME = next((x["name"] for x in json.load(open("/home/claude/fingod-company-data/pages/index.json")) if x.get("sym") == SYM), None)
    except Exception: NAME = None
NAME = (NAME or SYM).replace(" Limited", " Ltd")
Q = {datetime.strptime(k, "%Y-%m-%d"): v for k, v in H[B].items()}
ks = sorted(Q)
lab = lambda d: d.strftime("%b-%y")
FH = 14.0                      # figure height in inches; every y below is "inches from the top"
Y = lambda i: 1 - i / FH
HH = lambda h: h / FH

def shift(d, m):
    y, mo = divmod(d.year * 12 + d.month - 1 - m, 12)
    mo += 1
    return min([k for k in ks if k.year == y and k.month == mo] or [None], default=None)

def mk(d):
    q = Q.get(d)
    if not q or q.get("revenue") in (None, 0) or q.get("ebitda") is None or q.get("pat") is None: return None
    return {"revenue": q["revenue"] * 10, "ebitda": q["ebitda"] * 10, "pat": q["pat"] * 10, "basis": "c"}   # rating works in Rs million

def rate_at(d):
    c, pv, y = mk(d), mk(shift(d, 3)) if shift(d, 3) else None, mk(shift(d, 12)) if shift(d, 12) else None
    if not (c and pv and y): return None
    yp = mk(shift(d, 15)) if shift(d, 15) else None
    try:
        r = v21.rate21(c, pv, y, yp)
    except Exception:
        return None
    return r if r.get("tier") else None

cur = ks[-1]
R = rate_at(cur)
hist = [(d, rate_at(d)) for d in ks[-8:]]
if R is None:
    raise SystemExit("not enough history for " + SYM)
tier = R["tier"]; m = R["m"]; parts = R["parts"]; tg = R["tags"]
c0, c1, c4 = Q[cur], Q[shift(cur, 3)], Q[shift(cur, 12)]
TC = T.RATING_COLORS.get(tier, T.MUTED)
LIGHT = {"g": "#e3f3ea", "r": "#fbe6e4", "m": "#eef1f5"}

def pc(a, b):
    return None if a is None or b is None or b == 0 else (a - b) / abs(b) * 100

def txt(x, y, s, **k):
    k.setdefault("va", "center")
    return fig.text(x, Y(y), s, **k)

def box(x, y, w, h, fc, ec="none", r=0.012, lw=1):
    fig.patches.append(FancyBboxPatch((x, Y(y + h)), w, HH(h), boxstyle=f"round,pad=0,rounding_size={r}", transform=fig.transFigure, facecolor=fc, edgecolor=ec, linewidth=lw))

def pill(xr, y, s, kind, w=0.085, h=0.5, fs=15):
    box(xr - w, y - h / 2, w, h, LIGHT[kind], r=0.010)
    txt(xr - w / 2, y, s, color={"g": T.GREEN, "r": T.RED, "m": T.MUTED}[kind], fontsize=fs, fontweight="bold", ha="center")

def kind(v, eps=0.05):
    return "m" if v is None or abs(v) <= eps else "g" if v > 0 else "r"

fig = plt.figure(figsize=(16, FH), dpi=100, facecolor=T.BG)
# ---- header band
box(0.03, 0.25, 0.94, 1.15, T.PANEL, T.BORDER, r=0.008)
box(0.03, 0.25, 0.010, 1.15, TC, r=0.003)
txt(0.06, 0.70, NAME, color=T.TEXT, fontsize=28, fontweight="bold")
txt(0.06, 1.11, f"{SYM}  |  {lab(cur)} results  |  {'Consolidated' if B == 'C' else 'Standalone'}  |  ₹ Crore", color=T.MUTED, fontsize=14)
box(0.60, 0.40, 0.20, 0.85, TC, r=0.010)
txt(0.70, 0.825, tier.upper(), color="#ffffff", fontsize=26, fontweight="bold", ha="center")
# ---- table: same five columns as the live result card
box(0.03, 1.55, 0.94, 4.15, T.PANEL, T.BORDER, r=0.008)
rx = [0.40, 0.52, 0.64, 0.775, 0.93]
cols = [lab(cur), lab(shift(cur, 3)), lab(shift(cur, 12)), "QoQ", "YoY"]
for x, c in zip(rx, cols):
    txt(x, 2.02, c, color=T.HEAD, fontsize=15, fontweight="bold", ha="right")
fig.add_artist(plt.Line2D([0.045, 0.955], [Y(2.32)] * 2, color=T.BORDER, linewidth=1.2, transform=fig.transFigure))
mgf = lambda q: q["ebitda"] / q["revenue"] * 100
items = [("Sales", "revenue"), ("Operating profit", "ebitda"), ("OPM %", "opm"), ("Net profit (PAT)", "pat"), ("EPS (₹)", "eps")]
y = 2.85
nc = False
for label, k in items:
    txt(0.05, y, label, color=T.TEXT, fontsize=18, fontweight="bold")
    if k == "opm":
        vals = [mgf(q) for q in (c0, c1, c4)]
        shown = [f"{v:.1f}%" for v in vals]
        chg = [vals[0] - vals[1], vals[0] - vals[2]]
        ch_txt = [f"{v:+.1f} pp" for v in chg]
    else:
        vals = [q.get(k) for q in (c0, c1, c4)]
        d = 2 if k == "eps" else 0
        shown = ["-" if v is None else f"{v:,.{d}f}" for v in vals]
        chg = [pc(vals[0], vals[1]), pc(vals[0], vals[2])]
        if k == "eps":      # same rule as the live card: EPS growth not comparable when it differs from PAT growth by more than 5 points
            pat_chg = [pc(c0.get("pat"), c1.get("pat")), pc(c0.get("pat"), c4.get("pat"))]
            chg = ["NC" if (a is not None and b is not None and abs(a - b) > 5) else a for a, b in zip(chg, pat_chg)]
            nc = "NC" in chg
        ch_txt = ["NC*" if v == "NC" else "-" if v is None else f"{v:+,.1f}%" for v in chg]
        chg = [None if v == "NC" else v for v in chg]
    for x, s in zip(rx[:3], shown):
        txt(x, y, s, color=T.TEXT, fontsize=18, fontweight="bold", ha="right")
    for x, v, s in zip(rx[3:], chg, ch_txt):
        if s == "NC*":
            box(x - 0.085, y - 0.25, 0.085, 0.5, "#fbf0dc", r=0.010)
            txt(x - 0.0425, y, s, color=T.AMBER, fontsize=15, fontweight="bold", ha="center")
        else:
            pill(x, y, s, kind(v))
    y += 0.58
if nc:
    txt(0.05, 5.46, "* NC = EPS growth not comparable (share count changed between the periods)", color=T.AMBER, fontsize=12)
# ---- trend chart: last five quarters, sales / operating profit / net profit
box(0.03, 5.85, 0.94, 3.65, T.PANEL, T.BORDER, r=0.008)
txt(0.05, 6.13, "LAST 5 QUARTERS TREND", color=T.HEAD, fontsize=12.5, fontweight="bold")
txt(0.95, 6.13, "each line has its own scale  |  ₹ Crore", color=T.MUTED, fontsize=11, ha="right")
rows = ks[-5:]
labels = [lab(d) for d in rows]
SER = [("Sales", "revenue", T.BLUE, "top"), ("Operating profit", "ebitda", T.AMBER, "bottom"), ("Net profit", "pat", T.GREEN, "bottom")]
ax = fig.add_axes([0.075, Y(9.18), 0.88, HH(2.65)], facecolor="none")
ax.set_zorder(5)
ax.set_xlim(-0.95, len(rows) - 0.6); ax.set_ylim(0, 3)
for bi, (name_, k, col, where) in enumerate(SER):      # each series in its own band, scaled on its own, so labels never collide
    off = 2 - bi
    vals = [Q[d].get(k) for d in rows]
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if not pts: continue
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    nz = lambda v: off + (0.5 if hi == lo else 0.18 + 0.50 * (v - lo) / (hi - lo))
    ax.axhline(off, color=T.BORDER, linewidth=0.8, zorder=1)
    ax.plot([i for i, _ in pts], [nz(v) for _, v in pts], color=col, linewidth=3.2, marker="o", markersize=8, markerfacecolor=col, markeredgecolor=T.PANEL, markeredgewidth=1.5, zorder=3)
    for i, v in pts:
        ax.annotate(f"{v:,.0f}", (i, nz(v)), xytext=(0, 10), textcoords="offset points", ha="center", va="bottom", color=col, fontsize=12.5, fontweight="bold", zorder=4)
    ax.text(-0.93, off + 0.45, name_.replace("Operating profit", "Op. profit"), color=col, fontsize=11, fontweight="bold", va="center", ha="left")
ax.set_yticks([])
ax.set_xticks(range(len(rows)))
ax.set_xticklabels(labels, color=T.HEAD, fontsize=12, fontweight="bold")
ax.tick_params(axis="x", length=0)
for sp in ax.spines.values():
    sp.set_visible(False)
# ---- bottom left: how the verdict is built (the v2 points that decide the tier)
box(0.03, 9.65, 0.55, 3.30, T.PANEL, T.BORDER, r=0.008)
txt(0.05, 9.93, "HOW THE VERDICT IS BUILT  (points earned out of the maximum)", color=T.HEAD, fontsize=12.5, fontweight="bold")
sg = lambda x: "-" if x is None else f"{x:+,.0f}%"
pp = lambda x: f"{x:+.1f} pp"
grp = [("Sales", ["rev_yoy", "rev_qoq"], [22, 7], f"YoY {sg(m['rev_yoy'])}  |  QoQ {sg(m['rev_qoq'])}"),
       ("Net profit", ["pat_yoy", "pat_qoq"], [23, 6], f"YoY {sg(m['pat_yoy'])}  |  QoQ {sg(m['pat_qoq'])}"),
       ("Operating profit & margin", ["eb_yoy", "eb_qoq", "m_yoy", "m_qoq"], [11, 5, 14, 8], f"Op. profit YoY {sg(m['ebitda_yoy'])}, QoQ {sg(m['ebitda_qoq'])}  |  margin {pp(m['margin_yoy_pts'])} YoY, {pp(m['margin_qoq_pts'])} QoQ")]
yy = 10.36
for name_, keys, mx, line in grp:
    got, tot = sum(parts.get(k, 0) for k in keys), sum(mx)
    frac = got / tot if tot else 0
    txt(0.05, yy, name_, color=T.TEXT, fontsize=15, fontweight="bold")
    bx, bw = 0.31, 0.19
    box(bx, yy - 0.13, bw, 0.26, T.BORDER, r=0.006)
    box(bx, yy - 0.13, max(0.006, bw * frac), 0.26, T.GREEN if frac >= 0.6 else T.AMBER if frac >= 0.35 else T.RED, r=0.006)
    txt(0.565, yy, f"{got:.0f} / {tot}", color=T.TEXT, fontsize=15, fontweight="bold", ha="right")
    txt(0.05, yy + 0.36, line, color=T.MUTED, fontsize=11)
    yy += 0.72
txt(0.05, 12.50, f"Score {R['score']:.0f} of 100" + ("  |  Blockbuster by the explosive-growth rule" if R["v2_tier"] == "Blockbuster" and R["score"] < 80 else f"  |  {R['v2_tier']} on score") + (f"  |  final after v2.1 rules: {tier}" if tier != R["v2_tier"] else ""), color=T.TEXT, fontsize=12.5, fontweight="bold")
rules = (R["caps"] or []) + (R["v21_notes"] or [])
txt(0.05, 12.80, ("Held back by: " + "; ".join(rules[:2]) + (" (+%d more)" % (len(rules) - 2) if len(rules) > 2 else "")) if rules else "No cap applied", color=T.AMBER if rules else T.GREEN, fontsize=10.5, fontweight="bold")
# ---- bottom right: tags + history
box(0.60, 9.65, 0.37, 3.30, T.PANEL, T.BORDER, r=0.008)
txt(0.62, 9.93, "TAGS  (do not change the verdict)", color=T.HEAD, fontsize=12.5, fontweight="bold")
TAGC = {"Ahead": T.GREEN, "Building": T.GREEN, "In line": T.MUTED, "Mixed": T.MUTED, "Flat": T.AMBER, "Behind": T.RED, "Fading": T.RED}
for j, (nm, val) in enumerate((("Versus expectation", tg.get("vs_expectation")), ("Momentum", tg.get("momentum")))):
    yq = 10.38 + j * 0.46
    txt(0.62, yq, nm, color=T.TEXT, fontsize=14, fontweight="bold")
    val = val or "n/a"
    box(0.82, yq - 0.17, 0.125, 0.34, TAGC.get(val, T.MUTED), r=0.008)
    txt(0.8825, yq, val, color="#ffffff", fontsize=12.5, fontweight="bold", ha="center")
txt(0.62, 11.38, "LAST QUARTERS", color=T.HEAD, fontsize=12.5, fontweight="bold")
qs_ = [d for d in (shift(cur, 3 * k) for k in (3, 2, 1, 0)) if d] if all(shift(cur, 3 * k) for k in (3, 2, 1)) else [d for d in ks[-4:]]
for i, d in enumerate(qs_):
    yq = 11.78 + i * 0.30
    r_ = rate_at(d); t_ = r_["tier"] if r_ else "n/a"
    txt(0.62, yq, lab(d), color=T.MUTED, fontsize=12, fontweight="bold")
    box(0.70, yq - 0.12, 0.12, 0.24, T.RATING_COLORS.get(t_, "#aab4c0"), r=0.008)
    txt(0.76, yq, t_, color="#ffffff", fontsize=10.5, fontweight="bold", ha="center")
    if d == cur:
        txt(0.835, yq, "latest", color=T.MUTED, fontsize=10.5)
txt(0.04, 13.50, "For educational purpose only. Not an investment advice.", color=T.MUTED, fontsize=11)
txt(0.96, 13.50, "PROTOTYPE  |  Verdict v2.1", color=T.AMBER, fontsize=10, ha="right")
T.brand(fig, x_right=0.962, top=Y(0.32), h_in=0.62)
T.frame(fig)
os.makedirs(OUT, exist_ok=True)
fig.savefig(os.path.join(OUT, f"verdict_v21_{SYM}.png"), facecolor=T.BG, dpi=150)
print(SYM, lab(cur), tier, "(v2:", R["v2_tier"] + ")", round(R["score"]), R["tags"], rules)
