"""Verdict card PROTOTYPE v2 (five-column table + 5-quarter trend chart + verdict build-up + history). Not wired into production.
usage: python3 scripts/verdict_card_v2.py [SYMBOL] [OUT_DIR]"""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.patches import FancyBboxPatch
import theme as T, verdict_v3 as v3

SYM = sys.argv[1] if len(sys.argv) > 1 else "ACMESOLAR"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
H = json.load(open(os.path.join(os.path.dirname(__file__), "..", "companydata", "_hist", SYM + ".json")))
B = "C" if H["C"] else "S"
NAME = H.get("name") or SYM
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

def feats(d):
    c, y, p = Q.get(d), Q.get(shift(d, 12)), Q.get(shift(d, 3))
    if not c or not y or not c.get("revenue") or not y.get("revenue"):
        return None
    g = lambda a, b: (a / b - 1) * 100 if b and b > 0 else None
    mg = lambda q: q["ebitda"] / q["revenue"] * 100
    return {"y_rev": y["revenue"], "y_pat": y["pat"], "pat": c["pat"], "rev_y": g(c["revenue"], y["revenue"]), "eb_y": g(c["ebitda"], y["ebitda"]),
            "mg": mg(c), "mg_y": mg(c) - mg(y), "mg_q": mg(c) - mg(p) if p and p.get("revenue") else None, "pat_y": g(c["pat"], y["pat"]),
            "pm_y": c["pat"] / c["revenue"] * 100 - y["pat"] / y["revenue"] * 100, "oi_share": None, "conv": None}

cur = ks[-1]
hist = [(d, v3.rate(feats(d)) if feats(d) else ("n/a", {}, None)) for d in ks[-8:]]
tier, pil, why = [x for d, x in hist if d == cur][0]
f = feats(cur)
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
txt(0.95, 6.13, "₹ Crore", color=T.MUTED, fontsize=11, ha="right")
rows = ks[-5:]
labels = [lab(d) for d in rows]
SER = [("Sales", "revenue", T.BLUE, "top"), ("Operating profit", "ebitda", T.AMBER, "bottom"), ("Net profit", "pat", T.GREEN, "bottom")]
lx = 0.40
for name_, k, col, where in SER:
    box(lx, 6.045, 0.012, 0.17, col, r=0.003)
    txt(lx + 0.018, 6.13, name_, color=T.TEXT, fontsize=12.5, fontweight="bold")
    lx += 0.17
ax = fig.add_axes([0.075, Y(9.18), 0.88, HH(2.65)], facecolor="none")
ax.set_zorder(5)
allv = [0.0]
for name_, k, col, where in SER:
    vals = [Q[d].get(k) for d in rows]
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    allv += [v for _, v in pts]
    ax.plot([i for i, _ in pts], [v for _, v in pts], color=col, linewidth=3.2, marker="o", markersize=8, markerfacecolor=col, markeredgecolor=T.PANEL, markeredgewidth=1.5, zorder=3)
    for i, v in pts:
        ax.annotate(f"{v:,.0f}", (i, v), xytext=(0, 11 if where == "top" else -11), textcoords="offset points", ha="center", va="bottom" if where == "top" else "top", color=col, fontsize=12, fontweight="bold", zorder=4)
top, bot = max(allv), min(allv)
span = (top - bot) or 1
ax.set_ylim(min(0, bot - span * 0.12), top + span * 0.16)
ax.set_xlim(-0.4, len(rows) - 0.6)
ax.axhline(0, color=T.BORDER, linewidth=1.2, zorder=1)
ax.grid(axis="y", color=T.BORDER, linewidth=0.6, alpha=0.9)
ax.set_axisbelow(True)
ax.set_xticks(range(len(rows)))
ax.set_xticklabels(labels, color=T.HEAD, fontsize=12, fontweight="bold")
ax.tick_params(axis="y", colors=T.TEXT, labelsize=12, length=0)
ax.tick_params(axis="x", length=0)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
for sp in ax.spines.values():
    sp.set_visible(False)
# ---- bottom left: how the verdict is built
box(0.03, 9.60, 0.55, 3.35, T.PANEL, T.BORDER, r=0.008)
txt(0.05, 9.90, "HOW THE VERDICT IS BUILT  (each score out of 100)", color=T.HEAD, fontsize=12.5, fontweight="bold")
sg = lambda x: "-" if x is None else f"{x:+,.0f}%"
expl = {"growth": f"Sales {sg(f['rev_y'])}  |  Operating profit {sg(f['eb_y'])}  (YoY)",
        "profit": f"Operating margin {f['mg']:.0f}%,  {f['mg_y']:+.1f} pp YoY",
        "quality": f"Net profit {sg(f['pat_y'])} YoY,  net margin {f['pm_y']:+.1f} pp"}
LAB = {"growth": "Growth", "profit": "Profitability", "quality": "Profit quality"}
yy = 10.45
for k in ("growth", "profit", "quality"):
    s = pil.get(k, 0)
    txt(0.05, yy, LAB[k], color=T.TEXT, fontsize=16, fontweight="bold")
    bx, bw = 0.21, 0.30
    box(bx, yy - 0.14, bw, 0.28, T.BORDER, r=0.006)
    box(bx, yy - 0.14, max(0.006, bw * s / 100), 0.28, T.GREEN if s >= 55 else T.AMBER if s >= 35 else T.RED, r=0.006)
    txt(0.56, yy, f"{s}", color=T.TEXT, fontsize=17, fontweight="bold", ha="right")
    txt(0.05, yy + 0.38, expl[k], color=T.MUTED, fontsize=11.5)
    yy += 0.80
txt(0.05, 12.72, ("Held back by: " + why) if why else "No cap applied: verdict follows the three scores", color=T.AMBER if why else T.GREEN, fontsize=12, fontweight="bold")
# ---- bottom right: history + tags
box(0.60, 9.60, 0.37, 3.35, T.PANEL, T.BORDER, r=0.008)
txt(0.62, 9.90, "LAST QUARTERS  (same rules every quarter)", color=T.HEAD, fontsize=12.5, fontweight="bold")
hr = [h for h in hist if h[1][0] != "n/a"][-6:]
for i, (d, (t, p_, w_)) in enumerate(hr):
    yq = 10.40 + i * 0.36
    txt(0.62, yq, lab(d), color=T.MUTED, fontsize=12.5, fontweight="bold")
    box(0.70, yq - 0.15, 0.12, 0.30, T.RATING_COLORS.get(t, "#aab4c0"), r=0.008)
    txt(0.76, yq, t, color="#ffffff", fontsize=11, fontweight="bold", ha="center")
    if d == cur:
        txt(0.835, yq, "latest", color=T.MUTED, fontsize=11)
txt(0.62, 12.72, "Versus expectation: no guidance on file    Momentum: see QoQ", color=T.MUTED, fontsize=10.5)
txt(0.04, 13.50, "For educational purpose only. Not an investment advice.", color=T.MUTED, fontsize=11)
txt(0.96, 13.50, "PROTOTYPE v2", color=T.AMBER, fontsize=10, ha="right")
T.brand(fig, x_right=0.962, top=Y(0.32), h_in=0.62)
T.frame(fig)
os.makedirs(OUT, exist_ok=True)
fig.savefig(os.path.join(OUT, f"verdict_v2_{SYM}.png"), facecolor=T.BG, dpi=150)
print(SYM, lab(cur), tier, pil, why)
