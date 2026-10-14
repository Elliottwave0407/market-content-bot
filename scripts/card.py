import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import theme
from theme import HEAD, BG, PANEL, BORDER, TEXT, MUTED, GREEN, RED, AMBER, BLUE, BAR_OLD, RATING_COLORS

def cr(v):
    return None if v is None else v / 10.0

def pct(a, b):
    # values are in Rs million; a base under Rs 1 crore (10) or a change above 1000% is not meaningful
    if a is None or b is None or b == 0 or a < 0 or b < 0:
        return None
    if abs(b) < 10:
        return None
    v = (a - b) / b * 100
    return None if abs(v) > 1000 else v

def pct_eps(a, b):
    # EPS is in rupees (not Rs million): no tiny-base rule, only sign and sanity checks
    if a is None or b is None or b <= 0 or a < 0:
        return None
    v = (a - b) / b * 100
    return None if abs(v) > 1000 else v

def fmt_pct(v):
    return "NA" if v is None else f"{v:+.1f}%"

def fmt_num(v, d=0):
    return "NA" if v is None else f"{v:,.{d}f}"

def opm(m):
    return None if not m or m.get("ebitda") is None or not m.get("revenue") else m["ebitda"] / m["revenue"] * 100

def rating(q):
    """Draft rule - to be tuned by the author. Score from growth direction and strength."""
    cur, prev, yago = q[0]["m"], q[1]["m"], q[4]["m"] if len(q) > 4 else None
    s = 0
    ry, py, pq = pct(cur["revenue"], yago["revenue"]) if yago else None, pct(cur["pat"], yago["pat"]) if yago else None, pct(cur["pat"], prev["pat"]) if prev else None
    for v, hi in ((ry, 10), (py, 15)):
        if v is not None:
            s += 1 if v >= hi else (-1 if v < 0 else 0)
    if pq is not None:
        s += 1 if pq > 0 else -1
    o, oy = opm(cur), opm(yago)
    if o is not None and oy is not None:
        s += 1 if o - oy > 0.25 else (-1 if o - oy < -0.25 else 0)
    return "Excellent" if s >= 3 else "Great" if s == 2 else "Good" if s == 1 else "OK" if s == 0 else "Weak"

def _has_nc(cur, prev, yago):
    for base in (prev, yago):
        if not base:
            continue
        e, pt = pct_eps(cur.get("eps"), base.get("eps")), pct(cur.get("pat"), base.get("pat"))
        if e is not None and pt is not None and abs(e - pt) > 5:
            return True
    return False

def render(name, ticker, basis, quarters, out_path, filed_note=""):
    """quarters: list of {'q': label, 'm': metrics-dict} newest first (index 0 = latest, 1 = QoQ base, 4 = YoY base)."""
    cur, prev = quarters[0]["m"], quarters[1]["m"]
    yago = quarters[4]["m"] if len(quarters) > 4 else None
    rate = rating(quarters)
    fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=BG)
    nfs = 30
    rend = fig.canvas.get_renderer()
    while nfs > 20:
        tt = fig.text(0.04, 0.925, name, fontsize=nfs, fontweight="bold")
        wd = tt.get_window_extent(rend).width / fig.dpi
        tt.remove()
        if wd <= 0.54 * 16:
            break
        nfs -= 1
    fig.text(0.04, 0.925, name, color=TEXT, fontsize=nfs, fontweight="bold", va="center")
    fig.text(0.04, 0.875, f"{ticker}  |  {quarters[0]['q']} results  |  {basis.capitalize()}  |  ₹ Crore", color=MUTED, fontsize=15, va="center")
    # rating badge
    fig.patches.append(FancyBboxPatch((0.625, 0.86), 0.20, 0.09, boxstyle="round,pad=0.005,rounding_size=0.02", transform=fig.transFigure, facecolor=RATING_COLORS[rate], edgecolor="none"))
    fig.text(0.725, 0.905, rate.upper(), color="#ffffff", fontsize=24, fontweight="bold", ha="center", va="center")
    fig.text(0.725, 0.868, "RATING (draft rule)", color="#ffffff", fontsize=9, ha="center", va="center")
    # table
    cols = ["", quarters[0]["q"], quarters[1]["q"], quarters[4]["q"] if yago else "YoY base", "QoQ", "YoY"]
    xs = [0.04, 0.32, 0.46, 0.60, 0.75, 0.88]
    top = 0.78
    fig.patches.append(FancyBboxPatch((0.03, 0.40), 0.94, 0.41, boxstyle="round,pad=0.003,rounding_size=0.01", transform=fig.transFigure, facecolor=PANEL, edgecolor=BORDER, linewidth=1))
    for x, c in zip(xs, cols):
        fig.text(x if x == xs[0] else x + 0.05, top, c, color=HEAD, fontsize=15, fontweight="bold", ha="left" if x == xs[0] else "right", va="center")
    money = [cr(m.get(k)) for m in (cur, prev, yago) if m for k in ("revenue", "ebitda", "pat") if m.get(k) is not None]
    md = 0 if money and max(abs(v) for v in money) >= 1000 else 1
    items = [("Sales", "revenue", md), ("Operating profit", "ebitda", md), ("OPM %", "opm", 1), ("Net profit (PAT)", "pat", md), ("EPS (₹)", "eps", 2)]
    y = top - 0.065
    for label, key, d in items:
        def val(m):
            if not m:
                return None
            if key == "opm":
                return opm(m)
            v = m.get(key)
            return v if key == "eps" else cr(v)
        c, p, yy = val(cur), val(prev), val(yago)
        if c is None and key in ("ebitda", "opm"):
            continue
        fig.text(xs[0], y, label, color=TEXT, fontsize=18, fontweight="bold", va="center")
        for x, v in ((xs[1], c), (xs[2], p), (xs[3], yy)):
            fig.text(x + 0.05, y, fmt_num(v, d) if key != "opm" else ("NA" if v is None else f"{v:.1f}%"), color=TEXT, fontsize=18, fontweight="bold", ha="right", va="center")
        for x, base in ((xs[4], p), (xs[5], yy)):
            if key == "opm":
                chg = None if c is None or base is None else c - base
                txt, col = ("NA", MUTED) if chg is None else (f"{chg:+.1f} pp", GREEN if chg > 0.05 else RED if chg < -0.05 else MUTED)
            else:
                chg = pct_eps(c, base) if key == "eps" else pct(c, base)
                if key == "eps":
                    pc, pb = (cur.get("pat"), (prev if base is p else yago) or {})
                    pat_chg = pct(pc, pb.get("pat") if isinstance(pb, dict) else None)
                    if chg is not None and pat_chg is not None and abs(chg - pat_chg) > 5:
                        chg = "NC"
                if chg == "NC":
                    txt, col = "NC*", AMBER
                else:
                    txt, col = ("NA", MUTED) if chg is None else (fmt_pct(chg), GREEN if chg > 0 else RED if chg < 0 else MUTED)
            fig.text(x + 0.05, y, txt, color=col, fontsize=18, fontweight="bold", ha="right", va="center")
        y -= 0.062
    # trend bars (oldest -> newest)
    rows = list(reversed(quarters))
    labels = [r["q"] for r in rows]
    for i, (title, key) in enumerate((("Sales", "revenue"), ("Net profit", "pat"), ("EPS (₹)", "eps"))):
        ax = fig.add_axes([0.05 + i * 0.315, 0.09, 0.27, 0.23], facecolor=BG)
        vals = [(r["m"] or {}).get(key) for r in rows]
        vals = [None if v is None else (v if key == "eps" else cr(v)) for v in vals]
        bars = ax.bar(range(len(vals)), [v or 0 for v in vals], color=[BLUE if j == len(vals) - 1 else BAR_OLD for j in range(len(vals))])
        for j, v in enumerate(vals):
            ax.text(j, (v or 0), "NA" if v is None else fmt_num(v, 2 if key == "eps" else md), ha="center", va="top" if (v is not None and v < 0) else "bottom", color=TEXT, fontsize=11, fontweight="bold")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, color=HEAD, fontsize=11, fontweight="bold")
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(title, color=TEXT, fontsize=15, fontweight="bold", loc="left")
        ax.margins(y=0.2)
    fig.text(0.05, 0.425, "* NC = EPS growth not comparable (share count changed between the periods)", color=AMBER, fontsize=12, ha="left", va="center") if _has_nc(cur, prev, yago) else None
    fig.text(0.04, 0.035, "Source: BSE filings. Auto-generated from filed numbers - verify with official filings. Not investment advice." + (f"  {filed_note}" if filed_note else ""), color=MUTED, fontsize=11, va="center")
    theme.brand(fig, x_right=0.968, top=0.985, h_in=1.0)
    theme.frame(fig)
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return rate


def render_stub(name, ticker, quarter, reason, out_path):
    """Card for a filing whose numbers cannot be shown (no data / inconsistent). Never shows numbers."""
    fig = plt.figure(figsize=(16, 6), dpi=100, facecolor=BG)
    fig.text(0.04, 0.80, name, color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, 0.68, f"{ticker}  |  {quarter} results filed", color=MUTED, fontsize=15, va="center")
    fig.patches.append(FancyBboxPatch((0.03, 0.18), 0.94, 0.38, boxstyle="round,pad=0.005,rounding_size=0.02", transform=fig.transFigure, facecolor=PANEL, edgecolor=BORDER, linewidth=1))
    fig.text(0.05, 0.37, "Numbers not shown: " + reason, color=AMBER, fontsize=18, va="center")
    fig.text(0.04, 0.07, "Source: BSE filings. Open the filing link in the caption for the figures. Not investment advice.", color=MUTED, fontsize=12, va="center")
    theme.brand(fig, h_in=0.9)
    theme.frame(fig)
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
