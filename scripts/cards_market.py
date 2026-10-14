"""Card formats for bulk/block deals, FII/DII flows and news/announcements (light theme)."""
import textwrap
import theme as T
from theme import BG, PANEL, BORDER, TEXT, MUTED, HEAD, GREEN, RED, AMBER, BLUE

def indian(n, d=0):
    """12345678 -> 1,23,45,678"""
    if n is None:
        return "NA"
    neg = n < 0
    s = f"{abs(n):.{d}f}"
    ip, _, fp = s.partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        ip = ",".join(parts + [tail])
    return ("-" if neg else "") + ip + (("." + fp) if fp else "")

def money(v, d=1):
    return "NA" if v is None else f"{v:,.{d}f}" if abs(v) < 1000 else indian(v, 0)

# ---------------------------------------------------------------- portrait helpers
def _hdr(fig, W, H, title, sub, accent=None, page=None):
    """Top accent strip + title + sub line (logo is added by T.save / T.brand)."""
    from matplotlib.patches import Rectangle as Rect
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    fig.patches.append(Rect((fx(0.06), fy(0.45)), 1 - 2 * fx(0.06), 0.35 / H, transform=fig.transFigure, facecolor=accent or T.NAVY, edgecolor="none", zorder=1))
    fig.text(fx(0.75), fy(1.25), title, color=TEXT, fontsize=40, fontweight="bold", va="center")
    fig.text(fx(0.75), fy(1.85), sub, color=MUTED, fontsize=17, fontweight="bold", va="center")
    if page:
        fig.text(fx(W - 0.75), fy(2.35), page, color=HEAD, fontsize=20, fontweight="bold", ha="right", va="center")

def _foot(fig, W, H, text, note=""):
    L, mw = 0.75, W - 1.5
    for k, ln in enumerate(_wrap(fig, text + (f"  {note}" if note else ""), 13, "normal", mw, 3)):
        fig.text(L / W, 1 - (H - 1.0 + 0.3 * k) / H, ln, color=MUTED, fontsize=13, va="center")

# ---------------------------------------------------------------- bulk / block deals (ALL deals, paged, portrait)
def _deals_page(items, date_label, page, pages, out_path, note=""):
    """items: list of (section, row, index_in_section). One portrait card, 3 lines per deal."""
    from matplotlib.patches import Rectangle as Rect
    W = 10.8
    sections = []
    for sec, r, i in items:
        if not sections or sections[-1][0] != sec:
            sections.append([sec, []])
        sections[-1][1].append((r, i))
    RH = 1.12
    H = 2.6 + sum(0.95 + RH * len(rs) + 0.25 for _, rs in sections) + 1.4
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "Bulk & Block Deals", f"{date_label}  |  NSE + BSE  |  net per client  |  ₹ Crore", page=f"{page}/{pages}" if pages > 1 else None)
    y = 2.6
    for sec, rs in sections:
        color, title = (GREEN, "NET BUYERS") if sec == "B" else (RED, "NET SELLERS")
        if rs[0][1] > 0:
            title += " (continued)"
        h = 0.95 + RH * len(rs)
        T.panel(fig, fx(0.45), fy(y + h), (W - 0.9) / W, h / H)
        fig.patches.append(Rect((fx(0.45), fy(y + 0.1)), (W - 0.9) / W, 0.1 / H, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=5))
        fig.text(fx(0.8), fy(y + 0.55), title, color=color, fontsize=22, fontweight="bold", va="center")
        yy = y + 1.15
        for k, (r, _) in enumerate(rs):
            ex = "NSE" if r.get("ex") == "N" else "BSE"
            if k:
                fig.patches.append(Rect((fx(0.8), fy(yy - 0.2)), (W - 1.6) / W, 0.015 / H, transform=fig.transFigure, facecolor=BORDER, edgecolor="none"))
            fig.text(fx(0.8), fy(yy), r["name"][:24], color=TEXT, fontsize=21, fontweight="bold", va="center")
            fig.text(fx(W - 0.8), fy(yy), f"₹{r['cr']:,.2f} Cr", color=color, fontsize=21, fontweight="bold", ha="right", va="center")
            fig.text(fx(0.8), fy(yy + 0.38), r["client"][:34], color=HEAD, fontsize=14.5, fontweight="bold", va="center")
            fig.text(fx(W - 0.8), fy(yy + 0.38), f"{indian(r['qty'])} @ ₹{r['price']:,.2f}", color=TEXT, fontsize=14.5, ha="right", va="center")
            st = "Stake NA" if r.get("stake") is None else f"Stake {r['stake']:.2f}%"
            mc = "Mcap NA" if r.get("mcap") is None else f"Mcap ₹{indian(r['mcap'])} Cr"
            fig.text(fx(0.8), fy(yy + 0.72), f"{ex}   |   {st}   |   {mc}", color=MUTED, fontsize=13, va="center")
            yy += RH
        y += h + 0.25
    _foot(fig, W, H, "Netted per client per exchange; algo/prop trades and deals under ₹0.1 Cr removed. For educational purpose only.", note)
    T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
    T.save(fig, out_path)

def render_deals(rows, date_label, out_prefix, note="", per_card=10):
    """ALL deals of the day, buyers then sellers (each by value, largest first), split over as many portrait cards as needed. Returns list of PNG paths."""
    buys = sorted([r for r in rows if r["side"] == "B"], key=lambda r: -r["cr"])
    sells = sorted([r for r in rows if r["side"] == "S"], key=lambda r: -r["cr"])
    flat = [("B", r, i) for i, r in enumerate(buys)] + [("S", r, i) for i, r in enumerate(sells)]
    if not flat:
        return []
    pages = -(-len(flat) // per_card)
    per = -(-len(flat) // pages)
    paths = []
    for k in range(pages):
        path = f"{out_prefix}_{k + 1}.png"
        _deals_page(flat[k * per:(k + 1) * per], date_label, k + 1, pages, path, note)
        paths.append(path)
    return paths

# ---------------------------------------------------------------- FII / DII (portrait: today + month-to-date nets)
def render_fii_dii(d, out_path, note=""):
    """d = {"date", "month", "fii": {"buy","sell","net"}, "dii": {...}, "mtd": [ {"date","fii_buy","fii_sell","fii_net","dii_buy","dii_sell","dii_net"} ... ] oldest first, today last}"""
    from matplotlib.patches import Rectangle as Rect
    W = 10.8
    mtd = d.get("mtd") or []
    shown = mtd[-14:]
    H = 2.6 + 4.7 + 1.0 + ((1.3 + 0.5 * (len(shown) + 1) + 0.4) if mtd else 0) + 1.4
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    _hdr(fig, W, H, "FII / DII Activity", f"{d['date']}  |  Cash segment  |  ₹ Crore")
    pw = (W - 0.9 - 0.3) / 2
    for i, (key, label) in enumerate((("fii", "FII / FPI"), ("dii", "DII"))):
        x0 = 0.45 + i * (pw + 0.3)
        v = d[key]
        net = v["net"]
        color = GREEN if net > 0 else RED if net < 0 else MUTED
        word = "NET BUYERS" if net > 0 else "NET SELLERS" if net < 0 else "FLAT"
        y0 = 2.6
        T.panel(fig, fx(x0), fy(y0 + 4.7), pw / W, 4.7 / H)
        fig.patches.append(Rect((fx(x0), fy(y0 + 0.1)), pw / W, 0.1 / H, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=5))
        fig.text(fx(x0 + 0.3), fy(y0 + 0.6), label, color=TEXT, fontsize=24, fontweight="bold", va="center")
        T.chip(fig, fx(x0 + 0.3), fy(y0 + 1.5), (pw - 0.6) / W, 0.5 / H, word, color, 17)
        fig.text(fx(x0 + pw / 2), fy(y0 + 2.25), f"{'+' if net > 0 else '-' if net < 0 else ''}₹{abs(net):,.0f}", color=color, fontsize=44, fontweight="bold", ha="center", va="center")
        fig.text(fx(x0 + pw / 2), fy(y0 + 2.8), "Crore (net)", color=MUTED, fontsize=15, fontweight="bold", ha="center", va="center")
        mx = max(v["buy"], v["sell"], 1)
        for j, (lab, val, col) in enumerate((("Buy", v["buy"], GREEN), ("Sell", v["sell"], RED))):
            yy = y0 + 3.3 + j * 0.65
            fig.text(fx(x0 + 0.3), fy(yy), f"{lab} ₹{val:,.0f} Cr", color=TEXT, fontsize=14, fontweight="bold", va="center")
            fig.patches.append(Rect((fx(x0 + 0.3), fy(yy + 0.36)), (pw - 0.6) * val / mx / W, 0.12 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
    comb = d["fii"]["net"] + d["dii"]["net"]
    fig.text(fx(0.75), fy(2.6 + 4.7 + 0.55), f"Combined FII + DII net: {'+' if comb > 0 else '-' if comb < 0 else ''}₹{abs(comb):,.0f} Cr  ({'net buying' if comb > 0 else 'net selling' if comb < 0 else 'flat'})", color=TEXT, fontsize=20, fontweight="bold", va="center")
    if mtd:
        y0 = 2.6 + 4.7 + 1.0
        h = 1.3 + 0.5 * (len(shown) + 1) + 0.2
        T.panel(fig, fx(0.45), fy(y0 + h), (W - 0.9) / W, h / H)
        fig.text(fx(0.8), fy(y0 + 0.45), f"Month to date  |  {d.get('month', '')}  |  net ₹ Cr", color=TEXT, fontsize=20, fontweight="bold", va="center")
        cx = {"d": 0.8, "f": 5.0, "i": 7.3, "t": W - 0.8}
        for t, key, ha in (("Date", "d", "left"), ("FII Net", "f", "right"), ("DII Net", "i", "right"), ("FII+DII", "t", "right")):
            fig.text(fx(cx[key]), fy(y0 + 1.0), t, color=HEAD, fontsize=16, fontweight="bold", ha=ha, va="center")
        sgn = lambda v: GREEN if v > 0 else RED if v < 0 else TEXT
        def row(yy, lab, fn, dn, shade=False):
            if shade:
                fig.patches.append(Rect((fx(0.6), fy(yy + 0.24)), (W - 1.2) / W, 0.48 / H, transform=fig.transFigure, facecolor="#e3eaf3", edgecolor="none"))
            fig.text(fx(cx["d"]), fy(yy), lab, color=TEXT, fontsize=17, fontweight="bold", va="center")
            for key, v in (("f", fn), ("i", dn), ("t", fn + dn)):
                fig.text(fx(cx[key]), fy(yy), f"{v:+,.0f}", color=sgn(v), fontsize=17, fontweight="bold", ha="right", va="center")
        yy = y0 + 1.5
        for r in shown:
            row(yy, r["date"], r["fii_net"], r["dii_net"]); yy += 0.5
        row(yy, "MTD total", sum(r["fii_net"] for r in mtd), sum(r["dii_net"] for r in mtd), True)
    _foot(fig, W, H, "For educational purpose only.", note)
    T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
    T.save(fig, out_path)

# ---------------------------------------------------------------- news / announcements / macro
def _wrap(fig, text, fs, weight, max_in, max_lines=None):
    """Wrap text to a width in inches using real glyph measurement."""
    r = fig.canvas.get_renderer()
    dpi = fig.dpi
    def w(s):
        tx = fig.text(0, 0, s, fontsize=fs, fontweight=weight)
        v = tx.get_window_extent(r).width / dpi
        tx.remove()
        return v
    lines, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        if cur and w(trial) > max_in:
            lines.append(cur); cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;") + " ..."
    return lines

def render_news(it, out_path, note=""):
    """Portrait news card (10.8 x up to 13.5 in). it = {tag, company, meta, headline, sub (optional key-figure line), bullets (list), source}.
    Falls back to it['detail'] text as one bullet-less paragraph if no bullets are given."""
    from matplotlib.patches import Rectangle as Rect
    W = 10.8
    tmp = T.new_fig(W, 13.5)
    L, R = 0.75, W - 0.75
    mw = R - L
    color = T.TAGS.get(it["tag"], T.TAGS["UPDATE"])
    comp = _wrap(tmp, it["company"], 40, "bold", mw, 2)
    head = _wrap(tmp, it["headline"], 33, "bold", mw, 4)
    sub = _wrap(tmp, it["sub"], 26, "bold", mw - 0.7, 3) if it.get("sub") else []
    bl = list(it.get("bullets") or [])
    if not bl and it.get("detail"):
        bl = [it["detail"]]
    bl_lines = [_wrap(tmp, b, 24, "normal", mw - 0.7, 3) for b in bl]
    plt = T.plt
    plt.close(tmp)
    def total(nb):
        h = 2.9 + 0.62 * len(comp) + 0.58 * len(head) + 0.35
        if sub:
            h += 0.5 + 0.46 * len(sub) + 0.4
        h += sum(0.5 + 0.42 * len(x) for x in bl_lines[:nb]) + (0.2 if nb else 0)
        return h + 1.5
    nb = len(bl_lines)
    while nb > 0 and total(nb) > 13.5:
        nb -= 1
    H = min(13.5, max(8.8, total(nb)))
    fig = T.new_fig(W, H)
    fy = lambda inch: 1 - inch / H
    fx = lambda inch: inch / W
    fig.patches.append(Rect((fx(0.06), fy(0.45)), 1 - 2 * fx(0.06), 0.35 / H, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=1))
    T.chip(fig, fx(L), fy(1.55), fx(0.30 * len(it["tag"]) + 0.7), 0.55 / H, it["tag"], color, 20)
    y = 2.35
    for ln in comp:
        fig.text(fx(L), fy(y), ln, color=TEXT, fontsize=40, fontweight="bold", va="center")
        y += 0.62
    fig.text(fx(L), fy(y), it["meta"], color=MUTED, fontsize=17, fontweight="bold", va="center")
    y += 0.4
    fig.patches.append(Rect((fx(L), fy(y)), mw / W, 0.03 / H, transform=fig.transFigure, facecolor=T.BORDER, edgecolor="none"))
    y += 0.5
    for ln in head:
        fig.text(fx(L), fy(y), ln, color=T.HEAD, fontsize=33, fontweight="bold", va="center")
        y += 0.58
    y += 0.05
    if sub:
        h = 0.5 + 0.46 * len(sub)
        T.panel(fig, fx(L - 0.15), fy(y + h), (mw + 0.3) / W, h / H, fc=T.PANEL, ec=T.BORDER)
        fig.patches.append(Rect((fx(L - 0.15), fy(y + h)), 0.1 / W, h / H, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=5))
        yy = y + 0.25 + 0.23
        for ln in sub:
            fig.text(fx(L + 0.15), fy(yy), ln, color=color, fontsize=26, fontweight="bold", va="center")
            yy += 0.46
        y += h + 0.4
    for lines in bl_lines[:nb]:
        fig.patches.append(Rect((fx(L + 0.02), fy(y - 0.04) - 0.085 / H), 0.17 / W, 0.17 / H, transform=fig.transFigure, facecolor=color, edgecolor="none"))
        for k, ln in enumerate(lines):
            fig.text(fx(L + 0.5), fy(y - 0.04 + 0.42 * k), ln, color=TEXT, fontsize=24, va="center")
        y += 0.5 + 0.42 * (len(lines) - 1) + 0.0
        y += 0.0
    ft = "For educational purpose only." + (f"  {note}" if note else "")
    for k, ln in enumerate(_wrap(fig, ft, 13, "normal", mw, 2)):
        fig.text(fx(L), fy(H - 0.75 + 0.3 * k), ln, color=MUTED, fontsize=13, va="center")
    T.brand(fig, h_in=1.15, x_right=fx(R) + 0.0, top=fy(0.62) + 0.0)
    T.save(fig, out_path)

# ---------------------------------------------------------------- market breadth / mood
def mood_of(pct50):
    """Draft rule, printed on the card: % of liquid stocks closing above their 50-day average."""
    if pct50 is None:
        return "NA", MUTED
    if pct50 >= 65: return "STRONG", "#0f7a4b"
    if pct50 >= 50: return "POSITIVE", "#3a9a5b"
    if pct50 >= 35: return "MIXED", "#b97400"
    if pct50 >= 20: return "WEAK", "#c62f2f"
    return "VERY WEAK", "#8e1b1b"

def render_mood(b, out_path, note=""):
    """b = prices.breadth() output; uses the liquid universe."""
    from datetime import datetime
    L = b["liquid"]
    H = 9.4
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    Rect = __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle
    try:
        dl = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        dl = str(b["date"])
    label, mcol = mood_of(L.get("above_50"))
    fig.text(0.04, fy(0.55), "Market Breadth", color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{dl}  |  NSE stocks traded above ₹1 Cr  |  {L['n']:,} stocks", color=MUTED, fontsize=15, va="center")
    T.chip(fig, 0.74, fy(0.95), 0.22, 0.62 / H, f"MOOD: {label}", mcol, 20)
    # advance / decline
    T.panel(fig, 0.03, fy(3.35), 0.94, 1.95 / H)
    fig.text(0.045, fy(1.75), "Advancing vs declining", color=TEXT, fontsize=18, fontweight="bold", va="center")
    tot = max(L["adv"] + L["dec"] + L["unch"], 1)
    x0, wfull = 0.045, 0.91
    wa, wd, wu = wfull * L["adv"] / tot, wfull * L["dec"] / tot, wfull * L["unch"] / tot
    yb = fy(2.35)
    for x, w, c in ((x0, wa, GREEN), (x0 + wa, wu, "#9aa7b6"), (x0 + wa + wu, wd, RED)):
        fig.patches.append(Rect((x, yb), w, 0.42 / H, transform=fig.transFigure, facecolor=c, edgecolor="none"))
    fig.text(x0, fy(2.95), f"{L['adv']:,} up ({100 * L['adv'] / tot:.0f}%)", color=GREEN, fontsize=17, fontweight="bold", va="center")
    fig.text(0.5, fy(2.95), f"{L['unch']:,} unchanged", color=MUTED, fontsize=15, fontweight="bold", ha="center", va="center")
    fig.text(0.955, fy(2.95), f"{L['dec']:,} down ({100 * L['dec'] / tot:.0f}%)", color=RED, fontsize=17, fontweight="bold", ha="right", va="center")
    # % above moving averages
    T.panel(fig, 0.03, fy(6.35), 0.94, 2.75 / H)
    fig.text(0.045, fy(3.85), "Stocks trading above their moving average", color=TEXT, fontsize=18, fontweight="bold", va="center")
    for i, (k, lab) in enumerate((("above_20", "20-day"), ("above_50", "50-day"), ("above_200", "200-day"))):
        v = L.get(k)
        yy = 4.55 + i * 0.68
        fig.text(0.045, fy(yy), lab, color=HEAD, fontsize=16, fontweight="bold", va="center")
        fig.patches.append(Rect((0.15, fy(yy + 0.16)), 0.62, 0.32 / H, transform=fig.transFigure, facecolor="#dde4ec", edgecolor="none"))
        if v is not None:
            col = GREEN if v >= 60 else AMBER if v >= 40 else RED
            fig.patches.append(Rect((0.15, fy(yy + 0.16)), 0.62 * v / 100, 0.32 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
            fig.text(0.79, fy(yy), f"{v:.0f}%", color=col, fontsize=20, fontweight="bold", va="center")
    # highs / lows and big movers
    T.panel(fig, 0.03, fy(8.55), 0.94, 1.95 / H)
    items = (("52-week highs", L["new_high"], GREEN), ("52-week lows", L["new_low"], RED), ("Up 4%+ today", L["up4"], GREEN), ("Down 4%+ today", L["down4"], RED))
    for i, (lab, val, col) in enumerate(items):
        cx = 0.03 + 0.94 * (i + 0.5) / 4
        fig.text(cx, fy(6.95), f"{val:,}", color=col, fontsize=38, fontweight="bold", ha="center", va="center")
        fig.text(cx, fy(7.65), lab, color=HEAD, fontsize=15, fontweight="bold", ha="center", va="center")
    T.footer(fig, f"Mood rule: % of these stocks above their 50-day average (65+ Strong, 50+ Positive, 35+ Mixed, 20+ Weak). Derived from NSE end-of-day data. Not investment advice.{(' ' + note) if note else ''}", fy(H - 0.35))
    T.brand(fig, h_in=0.85)
    T.save(fig, out_path)

# ---------------------------------------------------------------- market breadth v2: aggregated + segregated (one card)
def render_mood2(b, out_path, note=""):
    """b = prices2.breadth_segments() output. Columns: All counted + each segment."""
    from datetime import datetime
    cols = [("All", b["all"], None)] + [(n, b["seg"][n], b["floors"][n]) for n in ("Large & Mid", "Small", "Micro", "SME")]
    H = 10.45
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    Rect = __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle
    try:
        dl = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        dl = str(b["date"])
    A = b["all"]
    label, mcol = mood_of(A.get("above_50"))
    fig.text(0.04, fy(0.55), "Market Breadth: All Segments", color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{dl}  |  NSE + BSE, each stock counted once  |  {A['n']:,} stocks counted of {b['traded_total']:,} traded", color=MUTED, fontsize=15, va="center")
    T.chip(fig, 0.745, fy(0.95), 0.215, 0.62 / H, f"OVERALL: {label}", mcol, 19)
    T.panel(fig, 0.03, fy(8.95), 0.94, 7.7 / H)
    xl = 0.045
    xs = [0.36 + i * 0.123 for i in range(5)]       # right edges of the 5 value columns
    y_head = 1.9
    fig.text(xl, fy(y_head), "", fontsize=12)
    for (name, st, floor), x in zip(cols, xs):
        fig.text(x, fy(y_head - 0.12), name, color=TEXT, fontsize=16, fontweight="bold", ha="right", va="center")
        fig.text(x, fy(y_head + 0.28), "all counted" if floor is None else ("min ₹%g Cr/day" % (floor / 100) if floor >= 100 else "min ₹%g L/day" % floor), color=MUTED, fontsize=11, ha="right", va="center")
    rows = [
        ("Stocks counted", lambda s: f"{s['n']:,}", None),
        ("Up", lambda s: f"{s['adv']:,}", GREEN),
        ("Down", lambda s: f"{s['dec']:,}", RED),
        ("Up share", lambda s: f"{100 * s['adv'] / max(s['n'], 1):.0f}%", "pct_up"),
        ("Above 20-day average", lambda s: "NA" if s["above_20"] is None else f"{s['above_20']:.0f}%", "pct"),
        ("Above 50-day average", lambda s: "NA" if s["above_50"] is None else f"{s['above_50']:.0f}%", "pct"),
        ("Above 200-day average", lambda s: "NA" if s["above_200"] is None else f"{s['above_200']:.0f}%", "pct"),
        ("52-week highs", lambda s: f"{s['new_high']:,}", GREEN),
        ("52-week lows", lambda s: f"{s['new_low']:,}", RED),
        ("Up 4%+ today", lambda s: f"{s['up4']:,}", GREEN),
        ("Down 4%+ today", lambda s: f"{s['down4']:,}", RED),
    ]
    y = 2.75
    step = 0.50
    for i, (lab, fn, col) in enumerate(rows):
        yy = y + i * step
        if i % 2 == 0:
            fig.patches.append(Rect((0.04, fy(yy + step / 2)), 0.92, step / H, transform=fig.transFigure, facecolor="#e9eff6", edgecolor="none"))
        fig.text(xl, fy(yy), lab, color=HEAD, fontsize=15, fontweight="bold", va="center")
        for (name, st, floor), x in zip(cols, xs):
            txt = fn(st)
            c = TEXT
            if col == "pct":
                v = float(txt[:-1]) if txt != "NA" else None
                c = MUTED if v is None else GREEN if v >= 60 else AMBER if v >= 40 else RED
            elif col == "pct_up":
                v = float(txt[:-1]); c = GREEN if v >= 55 else AMBER if v >= 45 else RED
            elif col:
                c = col
            fig.text(x, fy(yy), txt, color=c, fontsize=16, fontweight="bold", ha="right", va="center")
    yy = y + len(rows) * step + 0.12
    fig.text(xl, fy(yy), "Mood (50-day rule)", color=HEAD, fontsize=15, fontweight="bold", va="center")
    for (name, st, floor), x in zip(cols, xs):
        lab, c = mood_of(st.get("above_50"))
        T.chip(fig, x - 0.105, fy(yy + 0.2), 0.108, 0.40 / H, lab, c, 11)
    # right-hand side: advance/decline mini bars per segment
    for (name, st, floor), x in zip(cols, xs):
        pass
    f1 = "Segments: Large & Mid = market cap above ₹10,000 Cr; Small ₹2,000-10,000 Cr; Micro below ₹2,000 Cr (main board); SME = NSE Emerge + BSE SME."
    f2 = f"Mood: 65%+ Strong, 50%+ Positive, 35%+ Mixed, 20%+ Weak (stocks above their 50-day average). {b.get('unclassified', 0)} stocks without market cap are left out.{(' ' + note) if note else ''}"
    for k, t in enumerate((f1, f2, "Derived from NSE and BSE end-of-day data. Not investment advice.")):
        fig.text(0.04, fy(9.2 + 0.32 * k), t, color=MUTED, fontsize=11, va="center")
    T.brand(fig, h_in=0.85)
    T.save(fig, out_path)

# ---------------------------------------------------------------- market breadth v3: headline box + 3 segment boxes
def render_mood3(b, out_path, note=""):
    """b = prices2.breadth_segments() output (no liquidity floor by default)."""
    from datetime import datetime
    from matplotlib.patches import Rectangle as Rect
    H = 11.6
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    try:
        dl = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        dl = str(b["date"])
    A, S = b["all"], b["seg"]
    fig.text(0.04, fy(0.55), "Market Breadth", color=TEXT, fontsize=32, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{dl}  |  NSE + BSE, each company counted once  |  {A['n']:,} stocks traded today", color=MUTED, fontsize=15, va="center")

    def ud_bar(x, w, yin, st, h=0.34, fs=15):
        tot = max(st["adv"] + st["dec"] + st["unch"], 1)
        wa, wd, wu = w * st["adv"] / tot, w * st["dec"] / tot, w * st["unch"] / tot
        for xx, ww, c in ((x, wa, GREEN), (x + wa, wu, "#9aa7b6"), (x + wa + wu, wd, RED)):
            fig.patches.append(Rect((xx, fy(yin + h)), ww, h / H, transform=fig.transFigure, facecolor=c, edgecolor="none"))
        fig.text(x, fy(yin + h + 0.28), f"{st['adv']:,} up  ({100 * st['adv'] / tot:.0f}%)", color=GREEN, fontsize=fs, fontweight="bold", va="center")
        fig.text(x + w, fy(yin + h + 0.28), f"{st['dec']:,} down  ({100 * st['dec'] / tot:.0f}%)", color=RED, fontsize=fs, fontweight="bold", ha="right", va="center")

    # ---- headline box
    y0, hh = 1.45, 2.85
    label, mcol = mood_of(A.get("above_50"))
    T.panel(fig, 0.03, fy(y0 + hh), 0.94, hh / H)
    fig.patches.append(Rect((0.03, fy(y0 + 0.09)), 0.94, 0.09 / H, transform=fig.transFigure, facecolor=mcol, edgecolor="none"))
    fig.text(0.05, fy(y0 + 0.5), "Whole market", color=TEXT, fontsize=22, fontweight="bold", va="center")
    T.chip(fig, 0.755, fy(y0 + 0.72), 0.19, 0.46 / H, f"MOOD: {label}", mcol, 16)
    ud_bar(0.05, 0.90, y0 + 0.9, A)
    stats = [("Above 20-day", f"{A['above_20']:.0f}%" if A["above_20"] is not None else "NA"), ("Above 50-day", f"{A['above_50']:.0f}%" if A["above_50"] is not None else "NA"),
             ("Above 200-day", f"{A['above_200']:.0f}%" if A["above_200"] is not None else "NA"), ("52-week highs", f"{A['new_high']:,}"), ("52-week lows", f"{A['new_low']:,}")]
    for i, (lab, val) in enumerate(stats):
        cx = 0.05 + 0.90 * (i + 0.5) / 5
        col = TEXT
        if lab.startswith("Above") and val != "NA":
            v = float(val[:-1]); col = GREEN if v >= 60 else AMBER if v >= 40 else RED
        elif "highs" in lab: col = GREEN
        elif "lows" in lab: col = RED
        fig.text(cx, fy(y0 + 2.05), val, color=col, fontsize=30, fontweight="bold", ha="center", va="center")
        fig.text(cx, fy(y0 + 2.5), lab, color=HEAD, fontsize=13, fontweight="bold", ha="center", va="center")

    # ---- three segment boxes
    boxes = [("Large & Mid", "Market cap above ₹10,000 Cr", S["Large & Mid"]),
             ("Small & Micro", "Market cap below ₹10,000 Cr", S["Small & Micro"]),
             ("SME", "NSE Emerge + BSE SME", S["SME"])]
    by, bh, bw = 4.55, 6.0, 0.30
    for k, (name, sub, st) in enumerate(boxes):
        x = 0.03 + k * 0.32
        lab, c = mood_of(st.get("above_50"))
        T.panel(fig, x, fy(by + bh), bw, bh / H)
        fig.patches.append(Rect((x, fy(by + 0.09)), bw, 0.09 / H, transform=fig.transFigure, facecolor=c, edgecolor="none"))
        fig.text(x + 0.015, fy(by + 0.5), name, color=TEXT, fontsize=21, fontweight="bold", va="center")
        fig.text(x + 0.015, fy(by + 0.88), f"{sub}  |  {st['n']:,} stocks", color=MUTED, fontsize=11, va="center")
        T.chip(fig, x + 0.015, fy(by + 1.5), bw - 0.03, 0.46 / H, f"MOOD: {lab}", c, 15)
        ud_bar(x + 0.015, bw - 0.03, by + 1.8, st, h=0.30, fs=13)
        for i, (k2, lbl) in enumerate((("above_20", "20-day"), ("above_50", "50-day"), ("above_200", "200-day"))):
            v = st.get(k2)
            yy = by + 3.0 + i * 0.52
            fig.text(x + 0.015, fy(yy), lbl, color=HEAD, fontsize=13, fontweight="bold", va="center")
            fig.patches.append(Rect((x + 0.085, fy(yy + 0.13)), 0.14, 0.26 / H, transform=fig.transFigure, facecolor="#dde4ec", edgecolor="none"))
            if v is not None:
                col = GREEN if v >= 60 else AMBER if v >= 40 else RED
                fig.patches.append(Rect((x + 0.085, fy(yy + 0.13)), 0.14 * v / 100, 0.26 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
                fig.text(x + bw - 0.012, fy(yy), f"{v:.0f}%", color=col, fontsize=16, fontweight="bold", ha="right", va="center")
        fig.text(x + 0.015, fy(by + 2.72), "Above their average", color=MUTED, fontsize=11, va="center")
        for i, (val, lbl, col) in enumerate(((st["new_high"], "52-wk highs", GREEN), (st["new_low"], "52-wk lows", RED), (st["up4"], "Up 4%+", GREEN), (st["down4"], "Down 4%+", RED))):
            cx = x + bw * (i % 2 * 0.5 + 0.25)
            cy = by + 4.75 + (i // 2) * 0.72
            fig.text(cx - 0.012, fy(cy), f"{val:,}", color=col, fontsize=22, fontweight="bold", ha="right", va="center")
            fig.text(cx - 0.006, fy(cy), lbl, color=HEAD, fontsize=11, fontweight="bold", ha="left", va="center")
    f1 = "Mood rule: share of stocks above their 50-day average. 65%+ Strong, 50%+ Positive, 35%+ Mixed, 20%+ Weak. Every stock that traded on NSE or BSE today is included, once."
    f2 = f"{b.get('unclassified', 0)} stocks without a market cap are counted in the whole-market box only. Derived from NSE and BSE end-of-day data. Not investment advice.{(' ' + note) if note else ''}"
    for k, t in enumerate((f1, f2)):
        fig.text(0.04, fy(10.85 + 0.3 * k), t, color=MUTED, fontsize=10.5, va="center")
    T.brand(fig, h_in=0.85)
    T.save(fig, out_path)


# ---------------------------------------------------------------- market breadth v4: portrait
def render_mood4(b, out_path, note=""):
    """b = prices2.breadth_segments() output. Portrait: headline box + 3 stacked segment boxes."""
    from datetime import datetime
    from matplotlib.patches import Rectangle as Rect
    W = 10.8
    SEGH, TOPH = 3.75, 3.6
    H = 2.5 + TOPH + 0.3 + 3 * (SEGH + 0.25) + 1.9
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    try:
        dl = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        dl = str(b["date"])
    A, S = b["all"], b["seg"]
    _hdr(fig, W, H, "Market Breadth", f"{dl}  |  NSE + BSE  |  {A['n']:,} stocks")
    colr = lambda v: GREEN if v >= 60 else AMBER if v >= 40 else RED
    def pc(v):
        return "NA" if v is None else f"{v:.0f}%"
    def ud_bar(x, w, yin, st, h=0.4, fs=17):
        tot = max(st["adv"] + st["dec"] + st["unch"], 1)
        wa, wd, wu = w * st["adv"] / tot, w * st["dec"] / tot, w * st["unch"] / tot
        for xx, ww, c in ((x, wa, GREEN), (x + wa, wu, "#9aa7b6"), (x + wa + wu, wd, RED)):
            fig.patches.append(Rect((fx(xx), fy(yin + h)), ww / W, h / H, transform=fig.transFigure, facecolor=c, edgecolor="none"))
        fig.text(fx(x), fy(yin + h + 0.32), f"{st['adv']:,} up ({100 * st['adv'] / tot:.0f}%)", color=GREEN, fontsize=fs, fontweight="bold", va="center")
        fig.text(fx(x + w), fy(yin + h + 0.32), f"{st['dec']:,} down ({100 * st['dec'] / tot:.0f}%)", color=RED, fontsize=fs, fontweight="bold", ha="right", va="center")
    # headline
    y0 = 2.5
    label, mcol = mood_of(A.get("above_50"))
    T.panel(fig, fx(0.45), fy(y0 + TOPH), (W - 0.9) / W, TOPH / H)
    fig.patches.append(Rect((fx(0.45), fy(y0 + 0.1)), (W - 0.9) / W, 0.1 / H, transform=fig.transFigure, facecolor=mcol, edgecolor="none", zorder=5))
    fig.text(fx(0.8), fy(y0 + 0.6), "Whole market", color=TEXT, fontsize=26, fontweight="bold", va="center")
    T.chip(fig, fx(W - 0.8 - 3.3), fy(y0 + 0.88), 3.3 / W, 0.55 / H, f"MOOD: {label}", mcol, 20)
    ud_bar(0.8, W - 1.6, y0 + 1.1, A)
    stats = [("20-day", pc(A.get("above_20")), A.get("above_20")), ("50-day", pc(A.get("above_50")), A.get("above_50")), ("200-day", pc(A.get("above_200")), A.get("above_200"))]
    for i, (lab, val, v) in enumerate(stats):
        cx = 0.8 + (W - 1.6) * (i + 0.5) / 3
        fig.text(fx(cx), fy(y0 + 2.55), val, color=colr(v) if v is not None else TEXT, fontsize=40, fontweight="bold", ha="center", va="center")
        fig.text(fx(cx), fy(y0 + 3.0), f"above {lab}", color=HEAD, fontsize=16, fontweight="bold", ha="center", va="center")
    fig.text(fx(0.8), fy(y0 + 3.4), f"52-week highs {A['new_high']:,}   |   lows {A['new_low']:,}", color=HEAD, fontsize=16, fontweight="bold", va="center")
    # segments
    boxes = [("Large & Mid", "Market cap above ₹10,000 Cr", S["Large & Mid"]), ("Small & Micro", "Market cap below ₹10,000 Cr", S["Small & Micro"]), ("SME", "NSE Emerge + BSE SME", S["SME"])]
    by = y0 + TOPH + 0.3
    for name, sub, st in boxes:
        lab, c = mood_of(st.get("above_50"))
        T.panel(fig, fx(0.45), fy(by + SEGH), (W - 0.9) / W, SEGH / H)
        fig.patches.append(Rect((fx(0.45), fy(by + 0.1)), (W - 0.9) / W, 0.1 / H, transform=fig.transFigure, facecolor=c, edgecolor="none", zorder=5))
        fig.text(fx(0.8), fy(by + 0.55), name, color=TEXT, fontsize=25, fontweight="bold", va="center")
        fig.text(fx(0.8), fy(by + 0.98), f"{sub}  |  {st['n']:,} stocks", color=MUTED, fontsize=14, va="center")
        T.chip(fig, fx(W - 0.8 - 3.0), fy(by + 0.82), 3.0 / W, 0.5 / H, f"MOOD: {lab}", c, 18)
        ud_bar(0.8, W - 1.6, by + 1.3, st, h=0.34, fs=16)
        for i, (k2, lbl) in enumerate((("above_20", "20-day"), ("above_50", "50-day"), ("above_200", "200-day"))):
            v = st.get(k2)
            cx = 0.8 + (W - 1.6) * (i + 0.5) / 3
            fig.text(fx(cx), fy(by + 2.7), pc(v), color=colr(v) if v is not None else TEXT, fontsize=30, fontweight="bold", ha="center", va="center")
            fig.text(fx(cx), fy(by + 3.08), f"above {lbl}", color=HEAD, fontsize=14, fontweight="bold", ha="center", va="center")
        fig.text(fx(0.8), fy(by + 3.48), f"52-wk highs {st['new_high']:,}  |  lows {st['new_low']:,}  |  up 4%+ {st['up4']:,}  |  down 4%+ {st['down4']:,}", color=HEAD, fontsize=14, fontweight="bold", va="center")
        by += SEGH + 0.25
    _foot(fig, W, H, "Mood rule: share of stocks above their 50-day average - 65%+ Strong, 50%+ Positive, 35%+ Mixed, 20%+ Weak. For educational purpose only.", note)
    T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
    T.save(fig, out_path)
