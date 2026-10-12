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
            fig.text(0.045, fy(yy), f"{r['name'][:24]}", color=TEXT, fontsize=13, fontweight="bold", va="center")
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
    T.brand(fig, fy(H - 0.3))
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
    T.brand(fig, fy(H - 0.3))
    T.save(fig, out_path)

# ---------------------------------------------------------------- news / announcements / macro
def render_news(it, out_path, note=""):
    """it = {"tag": "ORDER WIN", "company": ..., "meta": "BSE 500325 | 12 Oct 2026, 16:20 IST", "headline": ..., "detail": optional text as filed, "source": "BSE announcement"}"""
    head = textwrap.wrap(it["headline"], 74)[:4]
    det = textwrap.wrap(it.get("detail") or "", 120)[:5] if it.get("detail") else []
    H = 3.3 + 0.62 * len(head) + (0.5 + 0.36 * len(det) if det else 0.2)
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    color = T.TAGS.get(it["tag"], T.TAGS["UPDATE"])
    T.chip(fig, 0.04, fy(0.95), 0.012 * len(it["tag"]) + 0.07, 0.5 / H, it["tag"], color, 15)
    fig.text(0.04, fy(1.45), it["company"], color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.95), it["meta"], color=MUTED, fontsize=14, fontweight="bold", va="center")
    y = 2.7
    for ln in head:
        fig.text(0.04, fy(y), ln, color=TEXT, fontsize=25, va="center")
        y += 0.62
    if det:
        h = 0.5 + 0.36 * len(det)
        T.panel(fig, 0.03, fy(y + 0.1 + h), 0.94, h / H)
        fig.text(0.05, fy(y + 0.38), "AS FILED", color=MUTED, fontsize=11, fontweight="bold", va="center")
        yy = y + 0.72
        for ln in det:
            fig.text(0.05, fy(yy), ln, color=TEXT, fontsize=14, va="center")
            yy += 0.36
    T.footer(fig, f"Source: {it.get('source', 'BSE announcement')}. Text as filed; read the full filing for details. Not investment advice." + (f"  {note}" if note else ""), fy(H - 0.3))
    T.brand(fig, fy(H - 0.3))
    T.save(fig, out_path)
