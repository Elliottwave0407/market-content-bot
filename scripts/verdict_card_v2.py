"""Verdict card PROTOTYPE v2 (full 5-column table like the live card + verdict build-up + history). Not wired into production.
usage: python3 scripts/verdict_card_v2.py [SYMBOL] [OUT_DIR]"""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

def txt(fig, x, y, s, **k):
    k.setdefault("va", "center")
    return fig.text(x, y, s, **k)

def pill(fig, xr, y, s, kind, w=0.085, h=0.040, fs=15):
    fig.patches.append(FancyBboxPatch((xr - w, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.012", transform=fig.transFigure, facecolor=LIGHT[kind], edgecolor="none"))
    txt(fig, xr - w / 2, y, s, color={"g": T.GREEN, "r": T.RED, "m": T.MUTED}[kind], fontsize=fs, fontweight="bold", ha="center")

def kind(v, eps=0.05):
    return "m" if v is None or abs(v) <= eps else "g" if v > 0 else "r"

fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=T.BG)
# ---- header band
fig.patches.append(FancyBboxPatch((0.03, 0.855), 0.94, 0.115, boxstyle="round,pad=0.002,rounding_size=0.014", transform=fig.transFigure, facecolor=T.PANEL, edgecolor=T.BORDER, linewidth=1))
fig.patches.append(FancyBboxPatch((0.03, 0.855), 0.012, 0.115, boxstyle="round,pad=0,rounding_size=0.004", transform=fig.transFigure, facecolor=TC, edgecolor="none"))
txt(fig, 0.06, 0.924, NAME, color=T.TEXT, fontsize=28, fontweight="bold")
txt(fig, 0.06, 0.880, f"{SYM}  |  {lab(cur)} results  |  {'Consolidated' if B == 'C' else 'Standalone'}  |  ₹ Crore", color=T.MUTED, fontsize=14)
T.chip(fig, 0.60, 0.868, 0.20, 0.088, tier.upper(), TC, fs=25)
txt(fig, 0.70, 0.8605, "QUARTERLY VERDICT", color=T.MUTED, fontsize=9, ha="center")
# ---- table (same five columns as the live result card)
xs = [0.05, 0.31, 0.43, 0.55, 0.69, 0.82]   # label, then right-edge anchors for the 5 data columns below
rx = [0.40, 0.52, 0.64, 0.775, 0.93]
T.panel(fig, 0.03, 0.43, 0.94, 0.405)
cols = [lab(cur), lab(shift(cur, 3)), lab(shift(cur, 12)), "QoQ", "YoY"]
ytop = 0.805
for x, c in zip(rx, cols):
    txt(fig, x, ytop, c, color=T.HEAD, fontsize=15, fontweight="bold", ha="right")
fig.add_artist(plt.Line2D([0.045, 0.955], [ytop - 0.027, ytop - 0.027], color=T.BORDER, linewidth=1.2, transform=fig.transFigure))
mgf = lambda q: q["ebitda"] / q["revenue"] * 100
items = [("Sales", "revenue"), ("Operating profit", "ebitda"), ("OPM %", "opm"), ("Net profit (PAT)", "pat"), ("EPS (₹)", "eps")]
y = ytop - 0.066
for label, k in items:
    txt(fig, 0.05, y, label, color=T.TEXT, fontsize=18, fontweight="bold")
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
        ch_txt = ["-" if v is None else f"{v:+,.1f}%" for v in chg]
    for x, s in zip(rx[:3], shown):
        txt(fig, x, y, s, color=T.TEXT, fontsize=18, fontweight="bold", ha="right")
    for x, v, s in zip(rx[3:], chg, ch_txt):
        pill(fig, x, y, s, kind(v))
    y -= 0.062
# ---- bottom left: how the verdict is built
T.panel(fig, 0.03, 0.075, 0.55, 0.335)
txt(fig, 0.05, 0.385, "HOW THE VERDICT IS BUILT  (each score out of 100)", color=T.HEAD, fontsize=12.5, fontweight="bold")
sg = lambda x: "-" if x is None else f"{x:+,.0f}%"
expl = {"growth": f"Sales {sg(f['rev_y'])}  |  Operating profit {sg(f['eb_y'])}  (YoY)",
        "profit": f"Operating margin {f['mg']:.0f}%,  {f['mg_y']:+.1f} pp YoY",
        "quality": f"Net profit {sg(f['pat_y'])} YoY,  net margin {f['pm_y']:+.1f} pp"}
LAB = {"growth": "Growth", "profit": "Profitability", "quality": "Profit quality"}
yy = 0.325
for k in ("growth", "profit", "quality"):
    s = pil.get(k, 0)
    txt(fig, 0.05, yy + 0.012, LAB[k], color=T.TEXT, fontsize=16, fontweight="bold")
    bx, bw = 0.21, 0.30
    fig.patches.append(FancyBboxPatch((bx, yy + 0.002), bw, 0.026, boxstyle="round,pad=0,rounding_size=0.006", transform=fig.transFigure, facecolor=T.BORDER, edgecolor="none"))
    fig.patches.append(FancyBboxPatch((bx, yy + 0.002), max(0.006, bw * s / 100), 0.026, boxstyle="round,pad=0,rounding_size=0.006", transform=fig.transFigure, facecolor=T.GREEN if s >= 55 else T.AMBER if s >= 35 else T.RED, edgecolor="none"))
    txt(fig, 0.56, yy + 0.015, f"{s}", color=T.TEXT, fontsize=17, fontweight="bold", ha="right")
    txt(fig, 0.05, yy - 0.026, expl[k], color=T.MUTED, fontsize=11.5)
    yy -= 0.082
# held-back line
reason = why if why else "No cap applied: verdict follows the three scores"
txt(fig, 0.05, 0.103, ("Held back by: " if why else "") + reason, color=T.AMBER if why else T.GREEN, fontsize=12, fontweight="bold")
# ---- bottom right: history + tags
T.panel(fig, 0.60, 0.075, 0.37, 0.335)
txt(fig, 0.62, 0.385, "LAST QUARTERS  (same rules every quarter)", color=T.HEAD, fontsize=12.5, fontweight="bold")
hr = [h for h in hist if h[1][0] != "n/a"][-6:]
for i, (d, (t, p_, w_)) in enumerate(hr):
    yq = 0.340 - i * 0.034
    txt(fig, 0.62, yq, lab(d), color=T.MUTED, fontsize=12.5, fontweight="bold")
    T.chip(fig, 0.70, yq - 0.014, 0.12, 0.028, t, T.RATING_COLORS.get(t, "#aab4c0"), fs=11)
    if d == cur:
        txt(fig, 0.835, yq, "latest", color=T.MUTED, fontsize=11)
txt(fig, 0.62, 0.103, "Versus expectation: no guidance on file    Momentum: see QoQ", color=T.MUTED, fontsize=10.5)
txt(fig, 0.04, 0.035, "For educational purpose only. Not an investment advice.", color=T.MUTED, fontsize=11)
txt(fig, 0.96, 0.035, "PROTOTYPE v2", color=T.AMBER, fontsize=10, ha="right")
T.brand(fig, x_right=0.962, top=0.966, h_in=0.62)
T.frame(fig)
os.makedirs(OUT, exist_ok=True)
fig.savefig(os.path.join(OUT, f"verdict_v2_{SYM}.png"), facecolor=T.BG, dpi=150)
print(SYM, lab(cur), tier, pil, why)
