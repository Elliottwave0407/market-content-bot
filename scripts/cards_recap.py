"""Portrait evening-recap card: day tone + scored positive / negative announcements."""
import theme as T
from theme import TEXT, MUTED, HEAD, GREEN, RED, BORDER, PANEL
from cards_market import _wrap, _hdr

W = 10.8
L, R = 0.75, W - 0.75
MW = R - L
GREY = "#c9d0d8"

def _pips(fig, fx, fy, x, y, n, color):
    from matplotlib.patches import Rectangle as Rect
    for k in range(5):
        fig.patches.append(Rect((fx(x + k * 0.2), fy(y + 0.2)), 0.14 / W, 0.4 / fig.get_figheight(), transform=fig.transFigure, facecolor=color if k < n else GREY, edgecolor="none", zorder=5))

def _rows(items, tmp, show):
    out = []
    for x in items[:show]:
        nm = _wrap(tmp, x["company"], 22, "bold", MW - 1.6, 1)[0]
        ln = _wrap(tmp, x["line"], 18, "normal", MW - 1.3, 2)
        out.append((x, nm, ln))
    return out

def render_recap(d, out_path, note=""):
    from matplotlib.patches import Rectangle as Rect
    tmp = T.new_fig(W, 13.5)
    pos_n, neg_n = (8, 4)
    def height(pr, nr):
        h = 3.0 + 1.55 + 0.95 + 1.1
        for rows in (pr, nr):
            if rows:
                h += 0.85 + sum(0.58 + 0.33 * len(r[2]) for r in rows)
        return h + 1.4
    pr, nr = _rows(d["pos"], tmp, pos_n), _rows(d["neg"], tmp, neg_n)
    while height(pr, nr) > 20 and (len(pr) > 4 or len(nr) > 3):
        if len(pr) > 4 and len(pr) - 4 >= len(nr) - 3: pr = pr[:-1]
        else: nr = nr[:-1]
    more_p, more_n = len(d["pos"]) - len(pr), len(d["neg"]) - len(nr)
    T.plt.close(tmp)
    H = max(9.0, height(pr, nr) + (0.65 if more_p else 0) + (0.65 if more_n else 0))
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "Filings Recap", f"Major announcements  |  {d['date']}")
    # stat tiles
    y = 3.0
    tiles = [("Filings scanned", f"{d['scanned']:,}", T.NAVY), ("Notable", str(d["notable"]), T.NAVY),
             ("Positive", str(len(d["pos"])), GREEN), ("Negative", str(len(d["neg"])), RED)]
    tw = (MW - 0.3 * 3) / 4
    for k, (lab, val, col) in enumerate(tiles):
        x0 = L + k * (tw + 0.3)
        T.panel(fig, fx(x0), fy(y + 1.25), tw / W, 1.25 / H, fc=PANEL, ec=BORDER)
        fig.text(fx(x0 + tw / 2), fy(y + 0.5), val, color=col, fontsize=34, fontweight="bold", ha="center", va="center")
        fig.text(fx(x0 + tw / 2), fy(y + 1.0), lab, color=MUTED, fontsize=15, fontweight="bold", ha="center", va="center")
    y += 1.55
    # tone bar
    p_, n_, z_ = len(d["pos"]), len(d["neg"]), d["neu"]
    tot = max(1, p_ + n_ + z_)
    sp = sum(x["score"] for x in d["pos"]); sn = -sum(x["score"] for x in d["neg"])
    tone = "POSITIVE" if sp > sn * 1.3 else "NEGATIVE" if sn > sp * 1.3 else "MIXED"
    tcol = GREEN if tone == "POSITIVE" else RED if tone == "NEGATIVE" else "#b97400"
    fig.text(fx(L), fy(y + 0.15), "Day's tone", color=MUTED, fontsize=17, fontweight="bold", va="center")
    fig.text(fx(L + 1.7), fy(y + 0.15), tone, color=tcol, fontsize=22, fontweight="bold", va="center")
    fig.text(fx(R), fy(y + 0.15), f"score points  +{sp}  /  -{sn}", color=MUTED, fontsize=17, fontweight="bold", ha="right", va="center")
    bx = L
    for cnt, col in ((p_, GREEN), (z_, GREY), (n_, RED)):
        wd = MW * cnt / tot
        if wd > 0:
            fig.patches.append(Rect((fx(bx), fy(y + 0.85)), wd / W, 0.3 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
        bx += wd
    y += 1.1
    # sections
    def section(title, rows, col, y):
        T.chip(fig, fx(L), fy(y + 0.6), fx(0.2 * len(title) + 1.0), 0.55 / H, title, col, 17)
        y += 0.85
        for k, (x, nm, ln) in enumerate(rows):
            h = 0.58 + 0.33 * len(ln)
            if k % 2 == 0:
                fig.patches.append(Rect((fx(L - 0.1), fy(y + h)), (MW + 0.2) / W, h / H, transform=fig.transFigure, facecolor="#f3efe6", edgecolor="none", zorder=0))
            fig.patches.append(Rect((fx(L - 0.1), fy(y + h)), 0.07 / W, h / H, transform=fig.transFigure, facecolor=col, edgecolor="none", zorder=1))
            fig.text(fx(L + 0.1), fy(y + 0.3), nm, color=col, fontsize=22, fontweight="bold", va="center")
            tg = x["tag"].title() + (f" (+{x['n'] - 1} more)" if x.get("n", 1) > 1 else "")
            fig.text(fx(R - 1.3), fy(y + 0.3), tg, color=MUTED, fontsize=13, fontweight="bold", ha="right", va="center")
            for j, l in enumerate(ln):
                fig.text(fx(L + 0.1), fy(y + 0.64 + 0.33 * j), l, color=TEXT, fontsize=18, va="center")
            _pips(fig, fx, fy, R - 1.05, y + h / 2, abs(x["score"]), col)
            y += h
        return y + 0.25
    def more(txt, y):
        fig.text(fx(L), fy(y + 0.25), txt, color=MUTED, fontsize=16, fontweight="bold", va="center")
        return y + 0.65
    if pr:
        y = section("POSITIVE CATALYSTS", pr, GREEN, y) - 0.25
        y = more(f"+ {more_p} more positive filings (lower scores)", y) if more_p else y + 0.25
    if nr:
        y = section("NEGATIVES / WATCH", nr, RED, y) - 0.25
        y = more(f"+ {more_n} more negative filings", y) if more_n else y + 0.25
    # mix + legend
    mix = "  |  ".join(f"{k.title()} {v}" for k, v in sorted(d["mix"].items(), key=lambda kv: -kv[1]))
    for k, ln in enumerate(_wrap(fig, "Filings by type:  " + mix, 15, "normal", MW, 2)):
        fig.text(fx(L), fy(y + 0.1 + 0.3 * k), ln, color=MUTED, fontsize=15, va="center")
    how = "AI-read from the filing text" if d.get("ai") else "rule-based from filing keywords"
    ft = f"Strength bars 1-5 = importance of the news ({how}); not a price forecast. For educational purpose only." + (f"  {note}" if note else "")
    for k, ln in enumerate(_wrap(fig, ft, 13, "normal", MW, 3)):
        fig.text(fx(L), fy(H - 0.9 + 0.3 * k), ln, color=MUTED, fontsize=13, va="center")
    T.save(fig, out_path)
