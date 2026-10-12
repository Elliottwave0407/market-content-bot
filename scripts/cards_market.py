"""Card formats for bulk/block deals, FII/DII flows and news/announcements (light theme)."""
import textwrap
import theme as T
from theme import BG, PANEL, BORDER, TEXT, MUTED, GREEN, RED, AMBER, BLUE

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

# ---------------------------------------------------------------- bulk / block deals
def render_deals(rows, date_label, out_path, note="", max_each=8):
    """rows: dicts with name, client, side ('B'/'S'), qty, price, cr (deal value Rs Cr), stake (% equity or None), mcap (Rs Cr or None), ex ('N'/'B')."""
    buys = sorted([r for r in rows if r["side"] == "B"], key=lambda r: -r["cr"])[:max_each]
    sells = sorted([r for r in rows if r["side"] == "S"], key=lambda r: -r["cr"])[:max_each]
    n = len(buys) + len(sells)
    H = 1.45 + sum(1.04 + 0.46 * len(d) + 0.18 for d in (buys, sells) if d) + 0.9
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    fig.text(0.04, fy(0.55), "Bulk & Block Deals", color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{date_label}  |  NSE + BSE  |  net per client  |  ₹ Crore", color=MUTED, fontsize=15, va="center")
    cols = [("Stock", 0.045, "left"), ("Client", 0.235, "left"), ("Qty", 0.60, "right"), ("Price ₹", 0.685, "right"), ("Value ₹Cr", 0.78, "right"), ("Stake %", 0.865, "right"), ("Mcap ₹Cr", 0.955, "right")]
    y = 1.45
    for title, data, color, word in (("NET BUYERS", buys, GREEN, "BUY"), ("NET SELLERS", sells, RED, "SELL")):
        if not data:
            continue
        h = 1.04 + 0.46 * len(data)
        T.panel(fig, 0.03, fy(y + h), 0.94, h / H)
        fig.text(0.045, fy(y + 0.30), title, color=color, fontsize=16, fontweight="bold", va="center")
        for t, x, ha in cols:
            fig.text(x, fy(y + 0.74), t, color=MUTED, fontsize=12, fontweight="bold", ha=ha, va="center")
        yy = y + 1.15
        for r in data:
            ex = "NSE" if r.get("ex") == "N" else "BSE"
            fig.text(0.045, fy(yy), f"{r['name'][:24]}", color=TEXT, fontsize=13, fontweight="bold", va="center")
            fig.text(0.235, fy(yy), f"{r['client'][:30]}", color=TEXT, fontsize=12.5, va="center")
            fig.text(0.60, fy(yy), indian(r["qty"]), color=TEXT, fontsize=13, ha="right", va="center")
            fig.text(0.685, fy(yy), f"{r['price']:,.2f}", color=TEXT, fontsize=13, ha="right", va="center")
            fig.text(0.78, fy(yy), f"{r['cr']:,.2f}", color=color, fontsize=13.5, fontweight="bold", ha="right", va="center")
            fig.text(0.865, fy(yy), "NA" if r.get("stake") is None else f"{r['stake']:.2f}", color=TEXT, fontsize=13, ha="right", va="center")
            fig.text(0.955, fy(yy), "NA" if r.get("mcap") is None else indian(r["mcap"]), color=TEXT, fontsize=13, ha="right", va="center")
            fig.text(0.215, fy(yy), ex, color=MUTED, fontsize=9, ha="right", va="center")
            yy += 0.46
        y += h + 0.18
    T.footer(fig, "Source: NSE & BSE bulk/block disclosures. Netted per client per exchange; algo/prop trades and deals under ₹0.1 Cr removed. Not investment advice." + (f"  {note}" if note else ""), fy(H - 0.3))
    T.brand(fig, fy(H - 0.3))
    T.save(fig, out_path)

# ---------------------------------------------------------------- FII / DII
def render_fii_dii(d, out_path, note=""):
    """d = {"date": "09 Oct 2026", "fii": {"buy","sell","net"}, "dii": {...}, "history": [{"date","fii","dii"}...] (optional, oldest first)}"""
    hist = d.get("history") or []
    H = 8.0 if not hist else 11.2
    fig = T.new_fig(16, H)
    fy = lambda inch: 1 - inch / H
    fig.text(0.04, fy(0.55), "FII / DII Activity", color=TEXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.04, fy(1.05), f"{d['date']}  |  Cash segment  |  ₹ Crore", color=MUTED, fontsize=15, va="center")
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
            fig.text(x0 + 0.02, fy(yy), lab, color=MUTED, fontsize=15, va="center")
            wbar = 0.26 * val / mx
            fig.patches.append(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle((x0 + 0.075, fy(yy + 0.14)), wbar, 0.28 / H, transform=fig.transFigure, facecolor=col, edgecolor="none"))
            fig.text(x0 + 0.075 + wbar + 0.008, fy(yy), f"₹{val:,.0f} Cr", color=TEXT, fontsize=15, va="center")
    comb = d["fii"]["net"] + d["dii"]["net"]
    fig.text(0.04, fy(5.4), f"Combined FII + DII net: {'+' if comb > 0 else '-' if comb < 0 else ''}₹{abs(comb):,.0f} Cr  ({'net buying' if comb > 0 else 'net selling' if comb < 0 else 'flat'})", color=TEXT, fontsize=17, va="center")
    if hist:
        import matplotlib.pyplot as plt
        ax = fig.add_axes([0.07, fy(10.35), 0.88, 4.0 / H], facecolor=BG)
        xs = range(len(hist))
        w = 0.36
        fv = [h["fii"] for h in hist]; dv = [h["dii"] for h in hist]
        ax.bar([x - w / 2 for x in xs], fv, w, color=BLUE, label="FII")
        ax.bar([x + w / 2 for x in xs], dv, w, color="#eb6834", label="DII")
        for x, a, b in zip(xs, fv, dv):
            for xx, val in ((x - w / 2, a), (x + w / 2, b)):
                ax.text(xx, val + (60 if val >= 0 else -60), f"{val:+,.0f}", ha="center", va="bottom" if val >= 0 else "top", color=TEXT, fontsize=10.5)
        ax.axhline(0, color=MUTED, linewidth=1)
        ax.set_xticks(list(xs)); ax.set_xticklabels([h["date"] for h in hist], color=MUTED, fontsize=12)
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.margins(y=0.25)
        ax.set_title(f"Net flows, last {len(hist)} sessions (₹ Cr)", color=TEXT, fontsize=15, loc="left")
        ax.legend(frameon=False, labelcolor=TEXT, fontsize=12, loc="upper right", ncol=2)
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
    fig.text(0.04, fy(1.95), it["meta"], color=MUTED, fontsize=14, va="center")
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
