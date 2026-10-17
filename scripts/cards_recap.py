"""One-card evening recap: the 20 most important filings (positives and negatives) as full sentences, with a signed impact score (-5..+5)."""
import theme as T
from theme import TEXT, MUTED, GREEN, RED, BORDER, PANEL
from cards_market import _wrap, _hdr

W = 10.8
L, R = 0.75, W - 0.75
MW = R - L
N_SHOW = 20
MAX_NEG = 7
SHORT = {"ORDER WIN": "ORDER", "ACQUISITION": "DEAL", "CREDIT RATING": "RATING", "CORPORATE ACTION": "ACTION", "DIVIDEND": "DIVIDEND", "MANAGEMENT": "MGMT", "RISK": "RISK"}
SF, SL = 16, 0.31

_FIG = [None]
LINE_W = MW - 0.85 - 0.1

def fits(text, fs=None):
    """True if the sentence fits on one line from the text margin to the right border."""
    if _FIG[0] is None:
        _FIG[0] = T.new_fig(W, 10)
    fig = _FIG[0]
    t = fig.text(0, 0, text, fontsize=fs or SF)
    w = t.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
    t.remove()
    return w <= LINE_W

def pick(d, n=N_SHOW):
    pos, neg = list(d["pos"]), list(d["neg"])
    k_neg = min(len(neg), MAX_NEG, max(n - len(pos), (n * 3) // 10))
    k_pos = min(len(pos), n - k_neg)
    k_neg = min(len(neg), n - k_pos)
    return pos[:k_pos], neg[:k_neg]

def render_recap(d, out_path, note=""):
    from matplotlib.patches import Rectangle as Rect, Ellipse
    fp, fn = pick(d)
    pos, neg = d["pos"], d["neg"]
    wrapped = {id(x): [x["line"]] for x in fp + fn}
    rowh = lambda x: 0.84
    top, tiles_h, tone_h, blk = 2.2, 1.0, 0.9, 0.58
    fii_h = 0.75 if d.get('fii') else 0
    H = top + tiles_h + tone_h + fii_h + (blk if fp else 0) + (blk if fn else 0) + sum(rowh(x) for x in fp + fn) + 1.45
    H = max(9.0, H)
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "Filings Recap", f"Top announcements  |  {d['date']}")
    y = top
    sp = sum(x["score"] for x in pos); sn = -sum(x["score"] for x in neg)
    c = d.get("cnt") or {}
    tiles = [("filings scanned", f"{d['scanned']:,}", T.NAVY), ("orders", str(c.get("orders", 0)), "#2a78d6"), ("deals", str(c.get("deals", 0)), "#6250d6"), ("risk / rating", str(c.get("alerts", 0)), RED)]
    tw = (MW - 0.25 * 3) / 4
    for k, (lab, val, col) in enumerate(tiles):
        x0 = L + k * (tw + 0.25)
        T.panel(fig, fx(x0), fy(y + tiles_h), tw / W, tiles_h / H, fc=PANEL, ec=BORDER)
        fig.text(fx(x0 + tw / 2), fy(y + 0.42), val, color=col, fontsize=30, fontweight="bold", ha="center", va="center")
        fig.text(fx(x0 + tw / 2), fy(y + 0.82), lab, color=MUTED, fontsize=14, fontweight="bold", ha="center", va="center")
    y += tiles_h + 0.25
    tone = "POSITIVE" if sp > sn * 1.3 else "NEGATIVE" if sn > sp * 1.3 else "MIXED"
    tcol = GREEN if tone == "POSITIVE" else RED if tone == "NEGATIVE" else "#b97400"
    fig.text(fx(L), fy(y + 0.2), "Day's tone", color=MUTED, fontsize=16, fontweight="bold", va="center")
    fig.text(fx(L + 1.55), fy(y + 0.2), tone, color=tcol, fontsize=21, fontweight="bold", va="center")
    fig.text(fx(R), fy(y + 0.2), f"net impact {sp - sn:+d}   (+{sp} / -{sn})", color=MUTED, fontsize=16, fontweight="bold", ha="right", va="center")
    tot = max(1, sp + sn)
    fig.patches.append(Rect((fx(L), fy(y + 0.78)), MW * sp / tot / W, 0.26 / H, transform=fig.transFigure, facecolor=GREEN, edgecolor="none"))
    fig.patches.append(Rect((fx(L + MW * sp / tot), fy(y + 0.78)), MW * sn / tot / W, 0.26 / H, transform=fig.transFigure, facecolor=RED, edgecolor="none"))
    y += tone_h
    if d.get("fii"):
        f = d["fii"]
        T.panel(fig, fx(L - 0.05), fy(y + 0.6), (MW + 0.1) / W, 0.6 / H, fc=PANEL, ec=BORDER)
        fig.text(fx(L + 0.15), fy(y + 0.3), f"FII / DII  {f['date']}", color=MUTED, fontsize=15, fontweight="bold", va="center")
        def cr(v):
            return ("+" if v >= 0 else "-") + f"\u20b9{abs(round(v)):,} Cr"
        col_f = GREEN if f["fii"] >= 0 else RED
        col_d = GREEN if f["dii"] >= 0 else RED
        t2 = fig.text(fx(R - 0.15), fy(y + 0.3), f"DII {cr(f['dii'])}", color=col_d, fontsize=17, fontweight="bold", ha="right", va="center")
        wd = t2.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
        fig.text(fx(R - 0.15 - wd - 0.4), fy(y + 0.3), f"FII {cr(f['fii'])}", color=col_f, fontsize=17, fontweight="bold", ha="right", va="center")
        y += fii_h
    rend = fig.canvas.get_renderer()
    def block(title, rows, col, y):
        T.chip(fig, fx(L), fy(y + 0.5), fx(0.2 * len(title) + 0.8), 0.46 / H, title, col, 15)
        y += blk
        for k, x in enumerate(rows):
            h = rowh(x)
            if k % 2 == 0:
                fig.patches.append(Rect((fx(L - 0.1), fy(y + h)), (MW + 0.2) / W, h / H, transform=fig.transFigure, facecolor="#f3efe6", edgecolor="none", zorder=0))
            sc = x["score"]
            c = GREEN if sc > 0 else RED if sc < 0 else "#7a8794"
            cx, cy = L + 0.3, y + 0.3
            fig.patches.append(Ellipse((fx(cx), fy(cy)), 0.52 / W, 0.52 / H, transform=fig.transFigure, facecolor=c, edgecolor="none", zorder=3))
            fig.text(fx(cx), fy(cy), f"{sc:+d}".replace("-", "−"), color="#ffffff", fontsize=15, fontweight="bold", ha="center", va="center", zorder=4)
            right = R
            tt = fig.text(fx(right), fy(y + 0.27), SHORT.get(x["tag"], x["tag"]), color=T.TAGS.get(x["tag"], T.NAVY), fontsize=12, fontweight="bold", ha="right", va="center")
            right -= tt.get_window_extent(rend).width / fig.dpi + 0.2
            key = x.get("key") or ""
            if key:
                kt = fig.text(fx(right), fy(y + 0.27), key, color=c, fontsize=15, fontweight="bold", ha="right", va="center")
                right -= kt.get_window_extent(rend).width / fig.dpi + 0.2
            more = ""
            nm = _wrap(fig, x["company"] + more, 17, "bold", right - (L + 0.7), 1)[0]
            fig.text(fx(L + 0.7), fy(y + 0.27), nm, color=TEXT, fontsize=17, fontweight="bold", va="center")
            for j, ln in enumerate(wrapped[id(x)]):
                fig.text(fx(L + 0.7), fy(y + 0.62 + SL * j), ln, color="#2c3b4c", fontsize=SF, va="center")
            y += h
        return y
    if fp:
        y = block("POSITIVE", fp, GREEN, y)
    if fn:
        y = block("NEGATIVE / WATCH", fn, RED, y + 0.05)
    how = "AI-read from the filing text" if d.get("ai") else "rule-based from filing keywords"
    ft = f"Top {len(fp) + len(fn)} of {len(d['pos']) + len(d['neg'])} important filings. Score -5 to +5 = likely importance of the news ({how}); not a price forecast. For educational purpose only." + (f"  {note}" if note else "")
    for k, ln in enumerate(_wrap(fig, ft, 13, "normal", MW, 3)):
        fig.text(fx(L), fy(H - 0.9 + 0.3 * k), ln, color=MUTED, fontsize=13, va="center")
    T.save(fig, out_path)
