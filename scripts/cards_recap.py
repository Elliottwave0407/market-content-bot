"""One-card evening recap, dense: tone strip, then every notable filing ranked by signed impact score (-5..+5)."""
import theme as T
from theme import TEXT, MUTED, GREEN, RED, BORDER, PANEL
from cards_market import _wrap, _hdr

W = 10.8
L, R = 0.75, W - 0.75
MW = R - L
ROW = 0.64
MAXH = 25.0
SHORT = {"ORDER WIN": "ORDER", "ACQUISITION": "DEAL", "CREDIT RATING": "RATING", "CORPORATE ACTION": "ACTION", "DIVIDEND": "DIVIDEND", "MANAGEMENT": "MGMT", "RISK": "RISK"}

def render_recap(d, out_path, note=""):
    from matplotlib.patches import Rectangle as Rect, Ellipse
    pos, neg, neu = d["pos"], d["neg"], d.get("neu_items", [])
    top = 2.35
    tiles_h, tone_h, blk = 1.05, 0.95, 0.62
    base = top + tiles_h + tone_h + 1.3
    tmp = T.new_fig(W, 10)
    # names of everything that does not get a full row go into one wrapped paragraph at the bottom
    def para_lines(names):
        if not names:
            return []
        return _wrap(tmp, "Also filed (score 0 / lower impact):  " + "  ·  ".join(names), 15, "normal", MW, 6)
    full_pos, full_neg = list(pos), list(neg)
    def height(fp, fn, rest):
        pl = para_lines(rest)
        return base + (blk if fp else 0) + (blk if fn else 0) + (len(fp) + len(fn)) * ROW + (0.35 + 0.3 * len(pl) if pl else 0)
    rest = [x["company"] for x in neu]
    while height(full_pos, full_neg, rest) > MAXH and (full_pos or full_neg):
        # push the weakest row into the paragraph
        cand = ([(abs(full_pos[-1]["score"]), "p")] if full_pos else []) + ([(abs(full_neg[-1]["score"]), "n")] if full_neg else [])
        w = min(cand)[1]
        x = full_pos.pop() if w == "p" else full_neg.pop()
        rest.insert(0, x["company"])
    pl = para_lines(rest)
    H = max(9.0, height(full_pos, full_neg, rest))
    T.plt.close(tmp)
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "Filings Recap", f"Major announcements  |  {d['date']}")
    y = top
    sp = sum(x["score"] for x in pos); sn = -sum(x["score"] for x in neg)
    tiles = [("scanned", f"{d['scanned']:,}", T.NAVY), ("notable", str(d["notable"]), T.NAVY), ("positive", str(len(pos)), GREEN), ("negative", str(len(neg)), RED)]
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
    rend = fig.canvas.get_renderer()
    def block(title, rows, col, y):
        T.chip(fig, fx(L), fy(y + 0.5), fx(0.2 * len(title) + 0.8), 0.46 / H, title, col, 15)
        y += blk
        for k, x in enumerate(rows):
            if k % 2 == 0:
                fig.patches.append(Rect((fx(L - 0.1), fy(y + ROW)), (MW + 0.2) / W, ROW / H, transform=fig.transFigure, facecolor="#f3efe6", edgecolor="none", zorder=0))
            sc = x["score"]
            c = GREEN if sc > 0 else RED if sc < 0 else "#7a8794"
            cx, cy = L + 0.3, y + ROW / 2
            fig.patches.append(Ellipse((fx(cx), fy(cy)), 0.52 / W, 0.52 / H, transform=fig.transFigure, facecolor=c, edgecolor="none", zorder=3))
            fig.text(fx(cx), fy(cy), f"{sc:+d}".replace("-", "−"), color="#ffffff", fontsize=15, fontweight="bold", ha="center", va="center", zorder=4)
            tg = SHORT.get(x["tag"], x["tag"])
            tcol_ = T.TAGS.get(x["tag"], T.NAVY)
            right = R
            tt = fig.text(fx(right), fy(y + 0.2), tg, color=tcol_, fontsize=12, fontweight="bold", ha="right", va="center")
            right -= tt.get_window_extent(rend).width / fig.dpi + 0.2
            key = x.get("key") or ""
            if key:
                kt = fig.text(fx(right), fy(y + 0.2), key, color=c, fontsize=15, fontweight="bold", ha="right", va="center")
                right -= kt.get_window_extent(rend).width / fig.dpi + 0.2
            more = f" (+{x['n'] - 1})" if x.get("n", 1) > 1 else ""
            nm = _wrap(fig, x["company"] + more, 16, "bold", right - (L + 0.7), 1)[0]
            fig.text(fx(L + 0.7), fy(y + 0.2), nm, color=TEXT, fontsize=16, fontweight="bold", va="center")
            ln = _wrap(fig, x["line"], 14, "normal", MW - 0.8, 1)[0]
            fig.text(fx(L + 0.7), fy(y + 0.47), ln, color="#2c3b4c", fontsize=14, va="center")
            y += ROW
        return y
    if full_pos:
        y = block("POSITIVE", full_pos, GREEN, y)
    if full_neg:
        y = block("NEGATIVE / WATCH", full_neg, RED, y + 0.05)
    if pl:
        y += 0.2
        for k, ln in enumerate(pl):
            fig.text(fx(L), fy(y + 0.15 + 0.3 * k), ln, color=MUTED, fontsize=15, va="center")
    how = "AI-read from the filing text" if d.get("ai") else "rule-based from filing keywords"
    ft = f"Score -5 to +5 = likely importance of the news ({how}); not a price forecast. For educational purpose only." + (f"  {note}" if note else "")
    for k, ln in enumerate(_wrap(fig, ft, 13, "normal", MW, 3)):
        fig.text(fx(L), fy(H - 0.9 + 0.3 * k), ln, color=MUTED, fontsize=13, va="center")
    T.save(fig, out_path)
