"""Verdict card PROTOTYPES (3 options) on real data. Not wired into production. usage: python3 scripts/verdict_card_protos.py [SYMBOL] [OUT_DIR]"""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import theme as T, verdict_v3 as v3
SYM = sys.argv[1] if len(sys.argv) > 1 else "ACMESOLAR"; OUT = sys.argv[2] if len(sys.argv) > 2 else "."
H = json.load(open(os.path.join(os.path.dirname(__file__), "..", "companydata", "_hist", SYM + ".json")))
B = "C" if H["C"] else "S"; DQ = sorted(H[B]); NAME = H.get("name") or SYM
Q = {datetime.strptime(k, "%Y-%m-%d"): v for k, v in H[B].items()}
ks = sorted(Q)
def lab(d): return d.strftime("%b-%y")
def shift(d, m):
    y, mo = divmod(d.year * 12 + d.month - 1 - m, 12); mo += 1
    return min([k for k in ks if k.year == y and k.month == mo] or [None], default=None)
def feats(d):
    c, y, p = Q.get(d), Q.get(shift(d, 12)), Q.get(shift(d, 3))
    if not c or not y or not c.get("revenue") or not y.get("revenue"): return None
    g = lambda a, b: (a / b - 1) * 100 if b and b > 0 else None
    mg = lambda q: q["ebitda"] / q["revenue"] * 100
    return {"y_rev": y["revenue"], "y_pat": y["pat"], "pat": c["pat"], "rev_y": g(c["revenue"], y["revenue"]), "eb_y": g(c["ebitda"], y["ebitda"]), "mg": mg(c), "mg_y": mg(c) - mg(y),
            "mg_q": mg(c) - mg(p) if p and p.get("revenue") else None, "pat_y": g(c["pat"], y["pat"]), "pm_y": c["pat"] / c["revenue"] * 100 - y["pat"] / y["revenue"] * 100,
            "oi_share": None, "conv": None}
cur = ks[-1]; hist = [(d, v3.rate(feats(d)) if feats(d) else ("n/a", {}, None)) for d in ks[-8:]]
tier, pil, why = [x for d, x in hist if d == cur][0]; f = feats(cur)
F = lambda x, d=0: "-" if x is None else f"{x:,.{d}f}"
sg = lambda x: "-" if x is None else f"{x:+,.0f}%"
col = lambda x: T.GREEN if x and x > 0 else T.RED if x and x < 0 else T.MUTED
def pc(a, b): return (a / b - 1) * 100 if b and b > 0 else None
c0, c1, c4 = Q[cur], Q[shift(cur, 3)], Q[shift(cur, 12)]
rows = [("Sales", "revenue"), ("Operating profit", "ebitda"), ("Net profit", "pat")]
def head(fig, option):
    fig.text(0.04, 0.925, NAME, color=T.TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, 0.875, f"{SYM}  |  {lab(cur)} results  |  Consolidated  |  ₹ Crore", color=T.MUTED, fontsize=15, va="center")
    fig.patches.append(FancyBboxPatch((0.625, 0.86), 0.20, 0.09, boxstyle="round,pad=0.005,rounding_size=0.02", transform=fig.transFigure, facecolor=T.RATING_COLORS.get(tier, T.MUTED), edgecolor="none"))
    fig.text(0.725, 0.905, tier.upper(), color="#fff", fontsize=24, fontweight="bold", ha="center", va="center")
    fig.text(0.725, 0.868, "QUARTERLY VERDICT", color="#fff", fontsize=10, ha="center", va="center")
    fig.text(0.04, 0.035, "For educational purpose only. Not an investment advice.", color=T.MUTED, fontsize=11, va="center")
    fig.text(0.96, 0.035, f"PROTOTYPE {option}", color=T.AMBER, fontsize=10, ha="right", va="center")
def table(fig, x0, x1, ytop, rowh=0.058):
    T.panel(fig, x0 - 0.01, ytop - 0.27, x1 - x0 + 0.02, 0.29)
    cx = [x0, x0 + (x1 - x0) * 0.44, x0 + (x1 - x0) * 0.60, x0 + (x1 - x0) * 0.76, x1]
    for x, t in zip(cx[1:], [lab(cur), "QoQ", "YoY", ""]): fig.text(x - 0.012, ytop, t, color=T.HEAD, fontsize=14, fontweight="bold", ha="right", va="center")
    y = ytop - 0.055
    for label, k in rows:
        fig.text(cx[0], y, label, color=T.TEXT, fontsize=16, fontweight="bold", va="center")
        fig.text(cx[1] - 0.012, y, F(c0[k]), color=T.TEXT, fontsize=16, fontweight="bold", ha="right", va="center")
        for x, base in ((cx[2], c1), (cx[3], c4)):
            ch = pc(c0[k], base[k]); fig.text(x - 0.012, y, sg(ch), color=col(ch), fontsize=16, fontweight="bold", ha="right", va="center")
        y -= rowh
    m = lambda q: q["ebitda"] / q["revenue"] * 100
    fig.text(cx[0], y, "Operating margin", color=T.TEXT, fontsize=16, fontweight="bold", va="center")
    fig.text(cx[1] - 0.012, y, f"{m(c0):.0f}%", color=T.TEXT, fontsize=16, fontweight="bold", ha="right", va="center")
    for x, base in ((cx[2], c1), (cx[3], c4)):
        d = m(c0) - m(base); fig.text(x - 0.012, y, f"{d:+.0f} pt", color=col(d), fontsize=16, fontweight="bold", ha="right", va="center")
def chart(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h], facecolor=T.BG); r = ks[-6:]
    for k, c_, n in (("revenue", T.BLUE, "Sales"), ("ebitda", T.AMBER, "Operating profit"), ("pat", T.GREEN, "Net profit")):
        vals = [Q[d][k] for d in r]; ax.plot(range(len(r)), vals, color=c_, linewidth=3, marker="o", markersize=7, label=n)
        for i, val in enumerate(vals): ax.annotate(f"{val:,.0f}", (i, val), xytext=(0, -17 if k == "ebitda" else 9), textcoords="offset points", ha="center", color=c_, fontsize=11, fontweight="bold")
    ax.set_ylim(0, max(Q[d]["revenue"] for d in r) * 1.18); ax.set_xticks(range(len(r))); ax.set_xticklabels([lab(d) for d in r], fontsize=11, fontweight="bold")
    ax.grid(axis="y", color=T.BORDER, linewidth=0.6); ax.tick_params(length=0, labelsize=11)
    for s in ax.spines.values(): s.set_visible(False)
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=11, bbox_to_anchor=(0, 1.12))
def pillar_expl():
    return {"growth": f"Sales {sg(f['rev_y'])}, operating profit {sg(f['eb_y'])} YoY", "profit": f"Margin {f['mg_y']:+.0f} pt YoY, {f['mg']:.0f}% level", "quality": f"Net profit {sg(f['pat_y'])} YoY, net margin {f['pm_y']:+.0f} pt"}
LAB = {"growth": "Growth", "profit": "Profitability", "quality": "Profit quality"}
def bars(fig, x0, ytop, w, rowh=0.085):
    T.panel(fig, x0 - 0.01, ytop - 0.32, w + 0.02, 0.35)
    fig.text(x0, ytop, "HOW THE VERDICT IS BUILT (score out of 100)", color=T.HEAD, fontsize=13, fontweight="bold", va="center")
    ex = pillar_expl(); y = ytop - 0.065
    for k in ("growth", "profit", "quality"):
        s = pil.get(k, 0); fig.text(x0, y + 0.012, LAB[k], color=T.TEXT, fontsize=16, fontweight="bold", va="center")
        fig.patches.append(FancyBboxPatch((x0 + 0.16, y + 0.004), w - 0.22, 0.026, boxstyle="round,pad=0,rounding_size=0.006", transform=fig.transFigure, facecolor=T.BORDER, edgecolor="none"))
        fig.patches.append(FancyBboxPatch((x0 + 0.16, y + 0.004), max(0.006, (w - 0.22) * s / 100), 0.026, boxstyle="round,pad=0,rounding_size=0.006", transform=fig.transFigure, facecolor=T.GREEN if s >= 55 else T.AMBER if s >= 35 else T.RED, edgecolor="none"))
        fig.text(x0 + w, y + 0.017, f"{s}", color=T.TEXT, fontsize=16, fontweight="bold", ha="right", va="center")
        fig.text(x0 + 0.16, y - 0.022, ex[k], color=T.MUTED, fontsize=11.5, va="center"); y -= rowh
def finish(fig, name):
    T.brand(fig, x_right=0.968, top=0.985, h_in=1.0); T.frame(fig); fig.savefig(os.path.join(OUT, name), facecolor=T.BG, dpi=150); plt.close(fig)
# ---- Option A: scorecard
fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=T.BG); head(fig, "A - Scorecard"); table(fig, 0.05, 0.47, 0.78); bars(fig, 0.53, 0.78, 0.42)
chart(fig, 0.08, 0.12, 0.86, 0.34); finish(fig, "verdict_A_scorecard.png")
# ---- Option B: verdict history ribbon + table + chart
fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=T.BG); head(fig, "B - History"); T.panel(fig, 0.03, 0.665, 0.94, 0.165)
fig.text(0.05, 0.805, "VERDICT HISTORY (same fixed rules every quarter)", color=T.HEAD, fontsize=13, fontweight="bold", va="center")
hr = [h for h in hist if h[1][0] != "n/a"]; cw = 0.88 / len(hr); xs = [0.05 + i * cw for i in range(len(hr))]
for x, (d, (t, p_, w_)) in zip(xs, hr):
    T.chip(fig, x, 0.69, cw - 0.01, 0.085, t, T.RATING_COLORS.get(t, "#aab4c0"), fs=15); fig.text(x + (cw - 0.01) / 2, 0.678, lab(d), color=T.MUTED, fontsize=11, ha="center", va="center")
table(fig, 0.05, 0.47, 0.60); fig.text(0.53, 0.60, "WHAT DECIDED IT", color=T.HEAD, fontsize=13, fontweight="bold", va="center")
ex = pillar_expl()
for i, k in enumerate(("growth", "profit", "quality")):
    fig.text(0.53, 0.54 - i * 0.07, f"{LAB[k]}  {pil.get(k,0)}/100", color=T.TEXT, fontsize=16, fontweight="bold", va="center"); fig.text(0.53, 0.512 - i * 0.07, ex[k], color=T.MUTED, fontsize=11.5, va="center")
chart(fig, 0.08, 0.12, 0.86, 0.17); finish(fig, "verdict_B_history.png")
# ---- Option C: rule checklist / ladder
fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=T.BG); head(fig, "C - Ladder"); table(fig, 0.05, 0.47, 0.78)
T.panel(fig, 0.51, 0.50, 0.46, 0.32)
fig.text(0.53, 0.795, "THE TEST FOR A TOP TIER", color=T.HEAD, fontsize=13, fontweight="bold", va="center")
checks = [("Sales growth 20%+ YoY", f"{sg(f['rev_y'])}", f["rev_y"] is not None and f["rev_y"] >= 20), ("Net profit growth 25%+ YoY", f"{sg(f['pat_y'])}", f["pat_y"] is not None and f["pat_y"] >= 25),
          ("Margin not lower than last year", f"{f['mg_y']:+.0f} pt", f["mg_y"] >= 0), ("Margin not down over 1 pt QoQ", f"{f['mg_q']:+.0f} pt" if f["mg_q"] is not None else "-", f["mg_q"] is None or f["mg_q"] >= -1),
          ("Every pillar at 55 or more", f"low {min(pil.values()) if pil else 0}", bool(pil) and min(pil.values()) >= 55)]
for i, (a, b, ok) in enumerate(checks):
    y = 0.74 - i * 0.045; fig.text(0.53, y, "✔" if ok else "✘", color=T.GREEN if ok else T.RED, fontsize=17, fontweight="bold", va="center"); fig.text(0.56, y, a, color=T.TEXT, fontsize=14.5, fontweight="bold", va="center"); fig.text(0.95, y, b, color=T.GREEN if ok else T.RED, fontsize=14.5, fontweight="bold", ha="right", va="center")
fail = [a for a, b, ok in checks if not ok]
fig.text(0.53, 0.52, ("Held at " + tier + " by: " + fail[0].lower()) if fail else "All top-tier tests met", color=T.AMBER if fail else T.GREEN, fontsize=13.5, fontweight="bold", va="center")
chart(fig, 0.08, 0.12, 0.86, 0.30); finish(fig, "verdict_C_ladder.png")
print(SYM, lab(cur), tier, pil, why)
