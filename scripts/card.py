import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib.patches import FancyBboxPatch
import theme
from theme import HEAD, BG, PANEL, BORDER, TEXT, MUTED, GREEN, RED, AMBER, BLUE, BAR_OLD, RATING_COLORS, BADGE_NAME
import quarter_rating as qr
import json, os
_CODE2SYM = None
def fin_kind(ticker):
    """'lender' / 'capmarket' / None from the card's ticker string ('NSE SYM' or 'BSE code')."""
    global _CODE2SYM
    try:
        kind, ref = str(ticker).split(" ", 1)
        if kind == "BSE":
            if _CODE2SYM is None:
                _CODE2SYM = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "symbols.json")))["m"]
            ref = _CODE2SYM.get(ref.strip(), "")
        ref = ref.strip().upper()
    except Exception:
        return None
    return "lender" if ref in qr.LENDERS else "capmarket" if ref in qr.CAPMARKET else None

def cr(v):
    return None if v is None else v / 10.0

def pct(a, b):
    # values are in Rs million; a base under Rs 1 crore (10) or a change above 1000% is not meaningful
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b) * 100      # abs(): a loss of 10 growing to 20 is -100%, 20 shrinking to 10 is +50%. Always the real figure (no small-base / size caps).

def pct_eps(a, b):
    # EPS is in rupees (not Rs million): no tiny-base rule, only sign and sanity checks
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b) * 100

def fmt_pct(v):
    return "-" if v is None else f"{v:+,.1f}%"

def fmt_num(v, d=0):
    return "-" if v is None else f"{v:,.{d}f}"

def opm(m):
    return None if not m or m.get("ebitda") is None or not m.get("revenue") else m["ebitda"] / m["revenue"] * 100

def rating(q, basis, yprev=None, half=False):
    """Quarter rating (Quarterly Verdict v2.0 = quarter_rating.rate6(v11, v12, v2)): Blockbuster / Excellent / Strong / Steady / Weak / Poor, or None when not ratable
    (missing numbers, no operating-profit row e.g. banks/NBFCs). q: newest-first quarters; basis: the one basis used for every quarter on the card."""
    mk = lambda i: dict(q[i]["m"], basis=basis) if len(q) > i and q[i].get("m") else None
    cur, prev, yago = mk(0), mk(1), mk(4)
    yprev = dict(yprev, basis=basis) if yprev else None      # the quarter before the year-ago one, for the seasonality adjustment (optional)
    if not (cur and prev and yago): return None
    return qr.rate6(cur, prev, yago, yprev, v11=True, half=half, v12=True, v2=True).get("tier")

def _has_nc(cur, prev, yago):
    for base in (prev, yago):
        if not base:
            continue
        e, pt = pct_eps(cur.get("eps"), base.get("eps")), pct(cur.get("pat"), base.get("pat"))
        if e is not None and pt is not None and abs(e - pt) > 5:
            return True
    return False

def render(name, ticker, basis, quarters, out_path, filed_note="", yprev=None, half=False):
    """quarters: list of {'q': label, 'm': metrics-dict} newest first (index 0 = latest, 1 = QoQ base, 4 = YoY base)."""
    lender = fin_kind(ticker) == "lender"
    if lender:      # a lender's net interest income (revenue - finance costs) stands in for operating profit
        quarters = [dict(q, m=(qr.to_lender(q.get("m")) or q.get("m"))) for q in quarters]
        yprev = qr.to_lender(yprev) or yprev
    for q_ in quarters:      # margin sanity: a margin beyond +-100% of sales is a data error, never show it
        m_ = q_.get("m") or {}
        if m_.get("ebitda") is not None and m_.get("revenue") and m_["revenue"] > 0 and abs(100 * m_["ebitda"] / m_["revenue"]) > 100:
            q_["m"] = dict(m_, ebitda=None)
    cur, prev = quarters[0]["m"], quarters[1]["m"]
    yago = quarters[4]["m"] if len(quarters) > 4 else None
    rate = rating(quarters, basis, yprev, half)
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
    # rating badge (omitted when the quarter is not ratable)
    if rate:
        fig.patches.append(FancyBboxPatch((0.625, 0.86), 0.20, 0.09, boxstyle="round,pad=0.005,rounding_size=0.02", transform=fig.transFigure, facecolor=RATING_COLORS[rate], edgecolor="none"))
        fig.text(0.725, 0.905, rate.upper(), color="#ffffff", fontsize=24, fontweight="bold", ha="center", va="center")
        fig.text(0.725, 0.868, "HALF-YEARLY VERDICT" if half else BADGE_NAME, color="#ffffff", fontsize=10, ha="center", va="center")
    # table
    cols = ["", quarters[0]["q"], quarters[1]["q"], quarters[4]["q"] if yago else "YoY base", "HoH" if half else "QoQ", "YoY"]
    xs = [0.04, 0.32, 0.46, 0.60, 0.75, 0.88]
    top = 0.78
    fig.patches.append(FancyBboxPatch((0.03, 0.40), 0.94, 0.41, boxstyle="round,pad=0.003,rounding_size=0.01", transform=fig.transFigure, facecolor=PANEL, edgecolor=BORDER, linewidth=1))
    for x, c in zip(xs, cols):
        fig.text(x if x == xs[0] else x + 0.05, top, c, color=HEAD, fontsize=15, fontweight="bold", ha="left" if x == xs[0] else "right", va="center")
    money = [cr(m.get(k)) for m in (cur, prev, yago) if m for k in ("revenue", "ebitda", "pat") if m.get(k) is not None]
    md = 0 if money and max(abs(v) for v in money) >= 1000 else 1
    kind_ = (cur or {}).get("kind")
    LBL = {"bank": ("Net total income", "Pre-provision profit", "PPOP margin %"), "life": ("Net premium", "Profit before tax", "PBT margin %"), "general": ("Net premium earned", "Profit before tax", "PBT margin %")}.get(kind_)
    items = [(LBL[0] if LBL else "Sales", "revenue", md), (LBL[1] if LBL else "Net interest income" if lender else "Operating profit", "ebitda", md), (LBL[2] if LBL else "NII margin %" if lender else "OPM %", "opm", 1), ("Net profit (PAT)", "pat", md), ("EPS (₹)", "eps", 2)]
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
            fig.text(x + 0.05, y, fmt_num(v, d) if key != "opm" else ("-" if v is None else f"{v:.1f}%"), color=TEXT, fontsize=18, fontweight="bold", ha="right", va="center")
        for x, base in ((xs[4], p), (xs[5], yy)):
            if key == "opm":
                chg = None if c is None or base is None else c - base
                txt, col = ("-", MUTED) if chg is None else (f"{chg:+.1f} pp", GREEN if chg > 0.05 else RED if chg < -0.05 else MUTED)
            else:
                chg = pct_eps(c, base) if key == "eps" else (None if c is None or base is None else pct(c * 10, base * 10))   # pct() expects Rs million (small-base rule = Rs 1 crore)
                if key == "eps":
                    pc, pb = (cur.get("pat"), (prev if base is p else yago) or {})
                    pat_chg = pct(pc, pb.get("pat") if isinstance(pb, dict) else None)
                    if chg is not None and pat_chg is not None and abs(chg - pat_chg) > 5:
                        chg = "NC"
                if chg == "NC":
                    txt, col = "NC*", AMBER
                else:
                    txt, col = ("-", MUTED) if chg is None else (fmt_pct(chg), GREEN if chg > 0 else RED if chg < 0 else MUTED)
            fig.text(x + 0.05, y, txt, color=col, fontsize=18, fontweight="bold", ha="right", va="center")
        y -= 0.062
    # trend lines (oldest -> newest): sales, operating margin and net profit in ONE chart, each line in its own band so labels never collide
    rows = list(reversed(quarters))
    labels = [r["q"] for r in rows]
    n = len(rows)
    g = lambda r, k: None if (r["m"] or {}).get(k) is None else cr(r["m"][k])
    ser = [((LBL[0] if LBL else "Sales"), [g(r, "revenue") for r in rows], BLUE, "top"),
           ((LBL[1] if LBL else "Operating profit"), [g(r, "ebitda") for r in rows], AMBER, "top"),
           ("Net profit", [g(r, "pat") for r in rows], GREEN, "bottom")]
    ax = fig.add_axes([0.07, 0.075, 0.68, 0.245], facecolor=BG)
    allv = [0.0]
    for k, (title, vals, col, where) in enumerate(ser):
        pts = [(i, v) for i, v in enumerate(vals) if v is not None]
        ly = 0.322 - k * 0.058
        fig.patches.append(FancyBboxPatch((0.775, ly - 0.009), 0.012, 0.017, boxstyle="round,pad=0,rounding_size=0.004", transform=fig.transFigure, facecolor=col, edgecolor="none"))
        fig.text(0.794, ly, title, color=TEXT, fontsize=12.5, fontweight="bold", va="center")
        if not pts:
            continue
        allv += [v for _, v in pts]
        ax.plot([i for i, _ in pts], [v for _, v in pts], color=col, linewidth=3.2, marker="o", markersize=8, markerfacecolor=col, markeredgecolor=BG, markeredgewidth=1.5, zorder=3)
    top = max(allv); bot = min(allv); span = (top - bot) or 1
    for title, vals, col, where in ser:
        for i, v in enumerate(vals):
            if v is None:
                continue
            ax.annotate(fmt_num(v, md), (i, v), xytext=(0, 11 if where == "top" else -11), textcoords="offset points", ha="center", va="bottom" if where == "top" else "top", color=col, fontsize=12, fontweight="bold", zorder=4)
    fig.text(0.96, 0.3655, "Rs Crore", color=MUTED, fontsize=11, ha="right", va="center")
    ax.set_ylim(min(0, bot - span * 0.12), top + span * 0.16)
    ax.set_xlim(-0.4, n - 0.6)
    ax.axhline(0, color=BORDER, linewidth=1.2, zorder=1)
    ax.grid(axis="y", color=BORDER, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, color=HEAD, fontsize=12, fontweight="bold")
    ax.tick_params(axis="y", colors=MUTED, labelsize=10, length=0)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.text(0.05, 0.425, "* NC = EPS growth not comparable (share count changed between the periods)", color=AMBER, fontsize=12, ha="left", va="center") if _has_nc(cur, prev, yago) else None
    fig.text(0.04, 0.035, "For educational purpose only. Not an investment advice.", color=MUTED, fontsize=11, va="center")
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
    fig.text(0.04, 0.07, "For educational purpose only. Not an investment advice.", color=MUTED, fontsize=12, va="center")
    theme.brand(fig, h_in=0.9)
    theme.frame(fig)
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
