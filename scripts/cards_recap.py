"""One-card evening recap: day tone + every notable filing grouped by type, each with a signed impact score (-5..+5)."""
import theme as T
from theme import TEXT, MUTED, GREEN, RED, BORDER, PANEL
from cards_market import _wrap, _hdr

W = 10.8
L, R = 0.75, W - 0.75
MW = R - L
ROW, SEC = 0.66, 0.85
MAXH = 24.0
ORDER = ["ORDER WIN", "ACQUISITION", "CREDIT RATING", "CORPORATE ACTION", "DIVIDEND", "MANAGEMENT", "RISK"]
LABEL = {"ORDER WIN": "ORDERS", "ACQUISITION": "DEALS & SCHEMES", "CREDIT RATING": "CREDIT RATINGS", "CORPORATE ACTION": "CORPORATE ACTIONS",
         "DIVIDEND": "DIVIDENDS", "MANAGEMENT": "MANAGEMENT CHANGES", "RISK": "RISK & DISTRESS"}

def _items(d):
    return d["pos"] + d["neg"] + d.get("neu_items", [])

def render_recap(d, out_path, note=""):
    from matplotlib.patches import Rectangle as Rect, Ellipse
    items = _items(d)
    base = 3.0 + 1.55 + 1.1 + 1.5
    # keep the strongest items that fit one card
    keep, cap = [], MAXH - base
    for x in sorted(items, key=lambda x: (-abs(x["score"]), x["company"])):
        tags_now = {k["tag"] for k in keep} | {x["tag"]}
        if (len(keep) + 1) * ROW + len(tags_now) * SEC + 0.6 <= cap:
            keep.append(x)
    dropped = len(items) - len(keep)
    groups = {}
    for x in keep:
        groups.setdefault(x["tag"], []).append(x)
    secs = [(t, sorted(groups[t], key=lambda x: (-x["score"], x["company"]))) for t in ORDER if t in groups]
    secs += [(t, v) for t, v in groups.items() if t not in ORDER]
    H = base + len(keep) * ROW + len(secs) * SEC + (0.6 if dropped else 0)
    H = max(9.0, H)
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "Filings Recap", f"Major announcements  |  {d['date']}")
    y = 3.0
    pos, neg = d["pos"], d["neg"]
    sp = sum(x["score"] for x in pos); sn = -sum(x["score"] for x in neg)
    tiles = [("Filings scanned", f"{d['scanned']:,}", T.NAVY), ("Notable", str(d["notable"]), T.NAVY),
             ("Positive", str(len(pos)), GREEN), ("Negative", str(len(neg)), RED)]
    tw = (MW - 0.3 * 3) / 4
    for k, (lab, val, col) in enumerate(tiles):
        x0 = L + k * (tw + 0.3)
        T.panel(fig, fx(x0), fy(y + 1.25), tw / W, 1.25 / H, fc=PANEL, ec=BORDER)
        fig.text(fx(x0 + tw / 2), fy(y + 0.5), val, color=col, fontsize=34, fontweight="bold", ha="center", va="center")
        fig.text(fx(x0 + tw / 2), fy(y + 1.0), lab, color=MUTED, fontsize=15, fontweight="bold", ha="center", va="center")
    y += 1.55
    net = sp - sn
    tone = "POSITIVE" if sp > sn * 1.3 else "NEGATIVE" if sn > sp * 1.3 else "MIXED"
    tcol = GREEN if tone == "POSITIVE" else RED if tone == "NEGATIVE" else "#b97400"
    fig.text(fx(L), fy(y + 0.15), "Day's tone", color=MUTED, fontsize=17, fontweight="bold", va="center")
    fig.text(fx(L + 1.7), fy(y + 0.15), tone, color=tcol, fontsize=22, fontweight="bold", va="center")
    fig.text(fx(R), fy(y + 0.15), f"net impact {net:+d}   (+{sp} / -{sn})", color=MUTED, fontsize=17, fontweight="bold", ha="right", va="center")
    tot = max(1, sp + sn)
    fig.patches.append(Rect((fx(L), fy(y + 0.85)), MW * sp / tot / W, 0.3 / H, transform=fig.transFigure, facecolor=GREEN, edgecolor="none"))
    fig.patches.append(Rect((fx(L + MW * sp / tot), fy(y + 0.85)), MW * sn / tot / W, 0.3 / H, transform=fig.transFigure, facecolor=RED, edgecolor="none"))
    y += 1.1
    tmp = fig
    for tag, rows in secs:
        col = T.TAGS.get(tag, T.NAVY)
        s_net = sum(x["score"] for x in rows)
        lab = LABEL.get(tag, tag)
        T.chip(fig, fx(L), fy(y + 0.62), fx(0.19 * len(lab) + 0.9), 0.5 / H, lab, col, 16)
        fig.text(fx(R), fy(y + 0.37), f"{len(rows)} shown   net {s_net:+d}", color=MUTED, fontsize=15, fontweight="bold", ha="right", va="center")
        y += SEC
        for k, x in enumerate(rows):
            if k % 2 == 0:
                fig.patches.append(Rect((fx(L - 0.1), fy(y + ROW)), (MW + 0.2) / W, ROW / H, transform=fig.transFigure, facecolor="#f3efe6", edgecolor="none", zorder=0))
            sc = x["score"]
            c = GREEN if sc > 0 else RED if sc < 0 else "#7a8794"
            cx, cy = L + 0.32, y + ROW / 2
            fig.patches.append(Ellipse((fx(cx), fy(cy)), 0.54 / W, 0.54 / H, transform=fig.transFigure, facecolor=c, edgecolor="none", zorder=3))
            fig.text(fx(cx), fy(cy), "0" if sc == 0 else f"{sc:+d}".replace("-", "−"), color="#ffffff", fontsize=15, fontweight="bold", ha="center", va="center", zorder=4)
            key = x.get("key") or ""
            kw = 0.0
            if key:
                kt = fig.text(fx(R), fy(y + 0.22), key, color=c if sc else TEXT, fontsize=15, fontweight="bold", ha="right", va="center")
                kw = kt.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi + 0.2
            nm = _wrap(fig, x["company"], 16, "bold", MW - 0.9 - kw, 1)[0]
            more = f"  (+{x['n'] - 1})" if x.get("n", 1) > 1 else ""
            fig.text(fx(L + 0.75), fy(y + 0.22), nm + more, color=TEXT, fontsize=16, fontweight="bold", va="center")
            ln = _wrap(fig, x["line"], 14, "normal", MW - 0.9, 1)[0]
            fig.text(fx(L + 0.75), fy(y + 0.50), ln, color="#2c3b4c", fontsize=14, va="center")
            y += ROW
        y += 0.0
    if dropped:
        fig.text(fx(L), fy(y + 0.3), f"+ {dropped} lower-impact filings not shown", color=MUTED, fontsize=15, fontweight="bold", va="center")
    how = "AI-read from the filing text" if d.get("ai") else "rule-based from filing keywords"
    ft = f"Score -5 to +5 = likely importance of the news ({how}); not a price forecast. For educational purpose only." + (f"  {note}" if note else "")
    for k, ln in enumerate(_wrap(fig, ft, 13, "normal", MW, 3)):
        fig.text(fx(L), fy(H - 0.9 + 0.3 * k), ln, color=MUTED, fontsize=13, va="center")
    T.save(fig, out_path)
