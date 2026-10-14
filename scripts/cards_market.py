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

# ---------------------------------------------------------------- bulk / block deals (ALL deals, paged)
def _deals_page(items, date_label, page, pages, out_path, note=""):
    """items: list of (section, row, index_in_section). One card."""
    sections = []
    for sec, r, i in items:
        if not sections or sections[-1][0] != sec:
            sections.append([sec, []])
        sections[-1][1].append((r, i))
    H = 1.45 + sum(1.04 + 0.46 * len(rs) + 0.18 for _, rs in sections) + 0.9
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    fig.text(0.04, fy(0.55), "Bulk & Block Deals", color=TEXT, fontsize=30, fontweight="bold", va="center")
    if pages > 1:
        fig.text(0.96, fy(0.55), f"{page}/{pages}", color=HEAD, fontsize=22, fontweight="bold", ha="right", va="center")
    fig.text(0.04, fy(1.05), f"{date_label}  |  NSE + BSE  |  net per client  |  ₹ Crore", color=MUTED, fontsize=15, va="center")
    cols = [("Stock", 0.045, "left"), ("Client", 0.235, "left"), ("Qty", 0.60, "right"), ("Price ₹", 0.685, "right"), ("Value ₹Cr", 0.78, "right"), ("Stake %", 0.865, "right"), ("Mcap ₹Cr", 0.955, "right")]
    y = 1.45
    for sec, rs in sections:
        color, title = (GREEN, "NET BUYERS") if sec == "B" else (RED, "NET SELLERS")
        if rs[0][1] > 0:
            title += " (continued)"
        h = 1.04 + 0.46 * len(rs)
        T.panel(fig, 0.03, fy(y + h), 0.94, h / H)
        fig.text(0.045, fy(y + 0.30), title, color=color, fontsize=16, fontweight="bold", va="center")
        for t, x, ha in cols:
            fig.text(x, fy(y + 0.74), t, color=HEAD, fontsize=12.5, fontweight="bold", ha=ha, va="center")
        yy = y + 1.15
        for r, _ in rs:
            ex = "NSE" if r.get("ex") == "N" else "BSE"
            fig.text(0.045, fy(yy), f"{r['name'][:19]}", color=TEXT, fontsize=13, fontweight="bold", va="center")
            fig.text(0.215, fy(yy), ex, color=MUTED, fontsize=9, fontweight="bold", ha="right", va="center")
            fig.text(0.235, fy(yy), f"{r['client'][:30]}", color=TEXT, fontsize=12.5, fontweight="bold", va="center")
            fig.text(0.60, fy(yy), indian(r["qty"]), color=TEXT, fontsize=13, fontweight="bold", ha="right", va="center")
            fig.text(0.685, fy(yy), f"{r['price']:,.2f}", color=TEXT, fontsize=13, fontweight="bold", ha="right", va="center")
            fig.text(0.78, fy(yy), f"{r['cr']:,.2f}", color=color, fontsize=13.5, fontweight="bold", ha="right", va="center")
            fig.text(0.865, fy(yy), "NA" if r.get("stake") is None else f"{r['stake']:.2f}", color=TEXT, fontsize=13, fontweight="bold", ha="right", va="center")
            fig.text(0.955, fy(yy), "NA" if r.get("mcap") is None else indian(r["mcap"]), color=TEXT, fontsize=13, fontweight="bold", ha="right", va="center")
            yy += 0.46
        y += h + 0.18
    T.footer(fig, "Source: NSE & BSE bulk/block disclosures. Netted per client per exchange; algo/prop trades and deals under ₹0.1 Cr removed. Not investment advice." + (f"  {note}" if note else ""), fy(H - 0.3))
    T.brand(fig, h_in=0.75)
    T.save(fig, out_path)

def render_deals(rows, date_label, out_prefix, note="", per_card=22):
    """ALL deals of the day, buyers then sellers (each by value, largest first), split over as many cards as needed. Returns list of PNG paths."""
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

# ---------------------------------------------------------------- FII / DII (today + month-to-date table)
def render_fii_dii(d, out_path, note=""):
    """d = {"date": "09 Oct 2026", "month": "Oct 2026", "fii": {"buy","sell","net"}, "dii": {...},
            "mtd": [ {"date": "01 Oct", "fii_buy","fii_sell","fii_net","dii_buy","dii_sell","dii_net"} ... ] (every trading day this month, oldest first, today last)}"""
    mtd = d.get("mtd") or []
    H = 6.2 + (1.9 + 0.40 * (len(mtd) + 1) if mtd else 0)
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    fig.text(0.04, fy(0.55), "FII / DII Activity", color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{d['date']}  |  Cash segment  |  ₹ Crore", color=MUTED, fontsize=15, va="center")
    Rect = __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle
    for i, (key, label) in enumerate((("fii", "FII / FPI"), ("dii", "DII"))):
        x0 = 0.03 + i * 0.48
        v = d[key]
        T.panel(fig, x0, fy(1.45 + 3.6), 0.46, 3.6 / H)
        net = v["net"]
        color = GREEN if net > 0 else RED if net < 0 else MUTED
        word = "NET BUYERS" if net > 0 else "NET SELLERS" if net < 0 else "FLAT"
        fig.text(x0 + 0.02, fy(1.95), label, color=TEXT, fontsize=22, fontweight="bold", va="center")
        T.chip(fig, x0 + 0.30, fy(2.15), 0.14, 0.40 / H, word, color, 14)
        fig.text(x0 + 0.02, fy(2.85), f"{'+' if net > 0 else '-' if net < 0 else ''}₹{abs(net):,.0f} Cr", color=color, fontsize=44, fontweight="bold", va="center")
        mx = max(v["buy"], v["sell"], 1)
        for j, (lab, val, col) in enumerate((("Buy", v["buy"], GREEN), ("Sell", v["sell"], RED))):
            yy = 3.75 + j * 0.62
            fig.text(x0 + 0.02, fy(yy), lab, color=HEAD, fontsize=15, fontweight="bold", va="center")
            wbar = 0.26 * val / mx
            fig.patches.append(Rect((x0 + 0.075, fy(yy + 0.14)), wbar, 0.28 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
            fig.text(x0 + 0.075 + wbar + 0.008, fy(yy), f"₹{val:,.0f} Cr", color=TEXT, fontsize=15, fontweight="bold", va="center")
    comb = d["fii"]["net"] + d["dii"]["net"]
    fig.text(0.04, fy(5.4), f"Combined FII + DII net: {'+' if comb > 0 else '-' if comb < 0 else ''}₹{abs(comb):,.0f} Cr  ({'net buying' if comb > 0 else 'net selling' if comb < 0 else 'flat'})", color=TEXT, fontsize=17, fontweight="bold", va="center")
    if mtd:
        y0 = 6.05
        h = 1.9 + 0.40 * (len(mtd) + 1) - 0.3
        T.panel(fig, 0.03, fy(y0 + h), 0.94, h / H)
        fig.text(0.045, fy(y0 + 0.35), f"Month to date  |  {d.get('month', '')}  |  ₹ Crore", color=TEXT, fontsize=17, fontweight="bold", va="center")
        cols = [("Date", 0.045, "left"), ("FII Buy", 0.26, "right"), ("FII Sell", 0.36, "right"), ("FII Net", 0.47, "right"),
                ("DII Buy", 0.64, "right"), ("DII Sell", 0.74, "right"), ("DII Net", 0.85, "right"), ("FII+DII", 0.955, "right")]
        for t, x, ha in cols:
            fig.text(x, fy(y0 + 0.85), t, color=HEAD, fontsize=13, fontweight="bold", ha=ha, va="center")
        def row(yy, lab, fb, fs, fn, db, ds, dn, bold_bg=False):
            if bold_bg:
                fig.patches.append(Rect((0.04, fy(yy + 0.19)), 0.92, 0.38 / H, transform=fig.transFigure, facecolor="#e3eaf3", edgecolor="none"))
            sgn = lambda v: GREEN if v > 0 else RED if v < 0 else TEXT
            fig.text(0.045, fy(yy), lab, color=TEXT, fontsize=13, fontweight="bold", va="center")
            for x, v, colr in ((0.26, fb, TEXT), (0.36, fs, TEXT), (0.47, fn, sgn(fn)), (0.64, db, TEXT), (0.74, ds, TEXT), (0.85, dn, sgn(dn)), (0.955, fn + dn, sgn(fn + dn))):
                fig.text(x, fy(yy), (f"{v:+,.0f}" if x in (0.47, 0.85, 0.955) else f"{v:,.0f}"), color=colr, fontsize=13, fontweight="bold", ha="right", va="center")
        yy = y0 + 1.3
        for r in mtd:
            row(yy, r["date"], r["fii_buy"], r["fii_sell"], r["fii_net"], r["dii_buy"], r["dii_sell"], r["dii_net"])
            yy += 0.40
        tot = lambda k: sum(r[k] for r in mtd)
        row(yy, "MTD total", tot("fii_buy"), tot("fii_sell"), tot("fii_net"), tot("dii_buy"), tot("dii_sell"), tot("dii_net"), True)
    T.footer(fig, "Source: exchange-reported provisional FII/DII cash-market data. Net = buy - sell. Not investment advice." + (f"  {note}" if note else ""), fy(H - 0.3))
    T.brand(fig, h_in=0.85)
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
    ft = f"{it.get('source', 'BSE announcement')}  |  Facts as filed - open the filing for details. Not investment advice." + (f"  {note}" if note else "")
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
