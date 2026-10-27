"""Candlestick chart card: candles + 20/50/200-day averages + volume + RSI + auto support/resistance + signal box.
Rule-based levels and signals from end-of-day data. For educational purpose only (no targets, no advice)."""
import numpy as np
import pandas as pd
import theme as T
from theme import TEXT, MUTED, HEAD, GREEN, RED, AMBER, BLUE, BORDER

C_MA = {"20": "#1f66c1", "50": "#d98a00", "200": "#7a3fb0"}

def rsi(close, n=14):
    d = close.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au, ad = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean(), dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))

def pivots(h, l, k=5):
    """Swing highs/lows: local extreme within +-k candles."""
    hs, ls = [], []
    for i in range(k, len(h) - k):
        if h.iloc[i] == h.iloc[i - k:i + k + 1].max():
            hs.append((i, float(h.iloc[i])))
        if l.iloc[i] == l.iloc[i - k:i + k + 1].min():
            ls.append((i, float(l.iloc[i])))
    return hs, ls

def levels(df, last, tol=0.025):
    """Cluster swing points into horizontal levels (>= 2 touches); return (supports below, resistances above), nearest first."""
    hs, ls = pivots(df["high"], df["low"])
    pts = sorted([p for _, p in hs] + [p for _, p in ls])
    clusters = []
    for p in pts:
        if clusters and p <= clusters[-1][-1] * (1 + tol):
            clusters[-1].append(p)
        else:
            clusters.append([p])
    lv = [(float(np.mean(c)), len(c)) for c in clusters if len(c) >= 2]
    sup = sorted([x for x in lv if x[0] < last * 0.995], key=lambda x: -x[0])[:2]
    res = sorted([x for x in lv if x[0] > last * 1.005], key=lambda x: x[0])[:2]
    return sup, res

def trendline(df, kind):
    """Line through the two latest swing lows (kind='low', must slope up) or swing highs (kind='high', must slope down), valid if price respected it."""
    hs, ls = pivots(df["high"], df["low"])
    pts = ls if kind == "low" else hs
    if len(pts) < 2:
        return None
    (i1, p1), (i2, p2) = pts[-2], pts[-1]
    if i2 - i1 < 8:
        return None
    if (kind == "low" and p2 <= p1) or (kind == "high" and p2 >= p1):
        return None
    m = (p2 - p1) / (i2 - i1)
    for j in range(i1, len(df)):
        y = p1 + m * (j - i1)
        if kind == "low" and df["close"].iloc[j] < y * 0.985:
            return None
        if kind == "high" and df["close"].iloc[j] > y * 1.015:
            return None
    return i1, p1, m

def signals(df, sup, res):
    c = df["close"]
    last = float(c.iloc[-1])
    out = []
    ma = {n: c.rolling(int(n)).mean() for n in ("20", "50", "200")}
    above = [n for n in ("20", "50", "200") if not np.isnan(ma[n].iloc[-1]) and last > ma[n].iloc[-1]]
    if len(above) == 3:
        out.append(("Trend", "Trading above its 20, 50 and 200-day averages", GREEN))
    elif not above:
        out.append(("Trend", "Trading below its 20, 50 and 200-day averages", RED))
    else:
        out.append(("Trend", f"Above the {' & '.join(above)}-day, below the rest of its averages", AMBER))
    if not np.isnan(ma["200"].iloc[-1]):
        d = (ma["50"] - ma["200"]).dropna()
        cross = None
        for j in range(len(d) - 1, max(len(d) - 21, 0), -1):
            if d.iloc[j] > 0 and d.iloc[j - 1] <= 0: cross = "Golden cross (50-day above 200-day) in the last 20 sessions"; break
            if d.iloc[j] < 0 and d.iloc[j - 1] >= 0: cross = "Death cross (50-day below 200-day) in the last 20 sessions"; break
        out.append(("Averages", cross or ("50-day average is above the 200-day" if d.iloc[-1] > 0 else "50-day average is below the 200-day"), GREEN if (cross and "Golden" in cross) else RED if cross else (GREEN if d.iloc[-1] > 0 else RED)))
    r = rsi(c).iloc[-1]
    zone = "overbought zone (above 70)" if r >= 70 else "oversold zone (below 30)" if r <= 30 else "neutral zone"
    out.append(("RSI (14)", f"{r:.0f} - {zone}", RED if r >= 70 else GREEN if r <= 30 else HEAD))
    hi, lo = float(df["high"].tail(250).max()), float(df["low"].tail(250).min())
    out.append(("52-week", f"{(last / hi - 1) * 100:.0f}% from the high (₹{hi:,.0f}); {(last / lo - 1) * 100:+.0f}% from the low (₹{lo:,.0f})", HEAD))
    va = float(df["vol"].tail(20).mean())
    if va > 0:
        x = float(df["vol"].iloc[-1]) / va
        out.append(("Volume", f"{x:.1f}x the 20-day average", GREEN if x >= 1.5 else HEAD))
    lv = []
    if sup: lv.append(f"Support ~₹{sup[0][0]:,.0f}")
    if res: lv.append(f"Resistance ~₹{res[0][0]:,.0f}")
    if lv:
        out.append(("Levels", "   |   ".join(lv) + "  (swing points)", HEAD))
    return out

def render(df, name, symbol, out_path, bars=120, note=""):
    """df: daily OHLCV (open, high, low, close, vol) for ONE stock, split-adjusted, sorted by date, with a 'date' column."""
    from matplotlib.patches import Rectangle as Rect
    import matplotlib.dates as mdates
    df = df.reset_index(drop=True)
    last = float(df["close"].iloc[-1]); prev = float(df["close"].iloc[-2])
    sup, res = levels(df.tail(250).reset_index(drop=True), last)
    sig = signals(df, sup, res)
    W = 10.8
    nsig = len(sig)
    H = 3.1 + 5.0 + 1.5 + 1.75 + 0.7 + 0.8 + nsig * 0.56 + 1.5
    fig = T.new_fig(W, H)
    fx = lambda i: i / W
    fy = lambda i: 1 - i / H
    chg = (last / prev - 1) * 100
    colr = GREEN if chg >= 0 else RED
    fig.patches.append(Rect((fx(0.06), fy(0.45)), 1 - 2 * fx(0.06), 0.35 / H, transform=fig.transFigure, facecolor=T.NAVY, edgecolor="none", zorder=1))
    fig.text(fx(0.75), fy(1.2), name, color=TEXT, fontsize=34, fontweight="bold", va="center")
    fig.text(fx(0.75), fy(1.75), f"NSE: {symbol}  |  Daily chart  |  {pd.to_datetime(df['date'].iloc[-1]).strftime('%d %b %Y')}", color=MUTED, fontsize=16, fontweight="bold", va="center")
    fig.text(fx(0.75), fy(2.45), f"₹{last:,.2f}", color=TEXT, fontsize=36, fontweight="bold", va="center")
    fig.text(fx(4.55), fy(2.45), f"{chg:+.2f}%", color=colr, fontsize=26, fontweight="bold", va="center")
    d = df.tail(bars).reset_index(drop=True)
    n = len(d)
    # ---- price panel
    top = 3.1
    ax = fig.add_axes([fx(0.75), fy(top + 5.0), (W - 1.5 - 0.95) / W, 5.0 / H])
    ma = {k: df["close"].rolling(int(k)).mean().tail(bars).reset_index(drop=True) for k in C_MA}
    for i in range(n):
        o, h, l, c = d.loc[i, ["open", "high", "low", "close"]]
        col = GREEN if c >= o else RED
        ax.plot([i, i], [l, h], color=col, linewidth=1.0, zorder=3)
        ax.add_patch(Rect((i - 0.32, min(o, c)), 0.64, max(abs(c - o), last * 0.0004), facecolor=col, edgecolor=col, zorder=4))
    for k, col in C_MA.items():
        ax.plot(range(n), ma[k], color=col, linewidth=1.8, label=f"{k}-day", zorder=5)
    # levels
    xr = n + 4
    for lvl, tch in sup:
        ax.axhline(lvl, color=GREEN, linestyle="--", linewidth=1.3, alpha=0.8, zorder=2)
        ax.text(0.5, lvl, f"Support ₹{lvl:,.0f}", color=GREEN, fontsize=11, fontweight="bold", va="bottom", bbox=dict(facecolor="white", edgecolor="none", pad=1.2, alpha=0.85), zorder=6)
    for lvl, tch in res:
        ax.axhline(lvl, color=RED, linestyle="--", linewidth=1.3, alpha=0.8, zorder=2)
        ax.text(0.5, lvl, f"Resistance ₹{lvl:,.0f}", color=RED, fontsize=11, fontweight="bold", va="bottom", bbox=dict(facecolor="white", edgecolor="none", pad=1.2, alpha=0.85), zorder=6)
    dd = df.tail(250).reset_index(drop=True)
    off = len(dd) - n
    for kind, col in (("low", GREEN), ("high", RED)):
        tl = trendline(dd, kind)
        if tl:
            i1, p1, m = tl
            x0 = max(i1 - off, 0)
            ax.plot([x0, n + 3], [p1 + m * (x0 + off - i1), p1 + m * (n + 3 + off - i1)], color=col, linewidth=1.6, alpha=0.85, zorder=2)
    ax.set_xlim(-1, xr)
    lo_, hi_ = float(d["low"].min()), float(d["high"].max())
    for k_ in C_MA:
        mv = ma[k_].dropna()
        if len(mv):
            lo_ = min(lo_, float(mv.min()) if float(mv.min()) > lo_ * 0.8 else lo_)
            hi_ = max(hi_, float(mv.max()) if float(mv.max()) < hi_ * 1.2 else hi_)
    pad = (hi_ - lo_) * 0.06
    ax.set_ylim(lo_ - pad, hi_ + pad)
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", labelsize=12, colors=HEAD, length=0)
    ax.tick_params(axis="x", length=0, labelbottom=False)
    ax.grid(axis="y", color=BORDER, linewidth=0.8)
    for s in ax.spines.values(): s.set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=12, frameon=False, ncol=3)
    # ---- volume
    axv = fig.add_axes([fx(0.75), fy(top + 5.0 + 1.5), (W - 1.5 - 0.95) / W, 1.3 / H], sharex=ax)
    axv.bar(range(n), d["vol"], color=[GREEN if c >= o else RED for o, c in zip(d["open"], d["close"])], width=0.7, alpha=0.75)
    axv.plot(range(n), df["vol"].rolling(20).mean().tail(bars).reset_index(drop=True), color=HEAD, linewidth=1.2)
    axv.set_yticks([]); axv.tick_params(length=0, labelbottom=False)
    for s in axv.spines.values(): s.set_visible(False)
    axv.text(0.005, 0.8, "Volume", transform=axv.transAxes, fontsize=11, color=MUTED, fontweight="bold", bbox=dict(facecolor="white", edgecolor="none", pad=1.5, alpha=0.9), zorder=10)
    # ---- RSI
    axr = fig.add_axes([fx(0.75), fy(top + 5.0 + 1.5 + 0.2 + 1.5), (W - 1.5 - 0.95) / W, 1.5 / H], sharex=ax)
    rs = rsi(df["close"]).tail(bars).reset_index(drop=True)
    axr.axhspan(30, 70, color="#eef2f7", zorder=0)
    axr.axhline(70, color=RED, linewidth=0.8, linestyle=":"); axr.axhline(30, color=GREEN, linewidth=0.8, linestyle=":")
    axr.plot(range(n), rs, color=BLUE, linewidth=1.8)
    axr.set_ylim(0, 100); axr.set_yticks([30, 70]); axr.yaxis.tick_right(); axr.tick_params(axis="y", labelsize=11, colors=HEAD, length=0)
    for s in axr.spines.values(): s.set_visible(False)
    axr.text(0.005, 0.8, "RSI (14)", transform=axr.transAxes, fontsize=11, color=MUTED, fontweight="bold")
    ticks, labs = [], []
    for i in range(n):
        dt = pd.to_datetime(d["date"].iloc[i])
        if i > 0 and dt.month != pd.to_datetime(d["date"].iloc[i - 1]).month:
            ticks.append(i); labs.append(dt.strftime("%b"))
    axr.set_xticks(ticks); axr.set_xticklabels(labs, fontsize=12, color=HEAD, fontweight="bold"); axr.tick_params(axis="x", length=0)
    # ---- signal box
    y0 = top + 5.0 + 1.5 + 0.2 + 1.5 + 0.7
    h = 0.75 + nsig * 0.56
    T.panel(fig, fx(0.45), fy(y0 + h), (W - 0.9) / W, h / H)
    fig.text(fx(0.8), fy(y0 + 0.4), "Chart read-out (rule-based)", color=TEXT, fontsize=19, fontweight="bold", va="center")
    for k, (lab, txt, col) in enumerate(sig):
        yy = y0 + 0.95 + k * 0.56
        fig.text(fx(0.8), fy(yy), lab, color=MUTED, fontsize=14, fontweight="bold", va="center")
        fig.text(fx(2.45), fy(yy), txt, color=col, fontsize=14.5, fontweight="bold", va="center")
    ft = "Levels and trendlines are drawn automatically from past swing points. Scan output, not a recommendation. For educational purpose only. Not an investment advice." + (f"  {note}" if note else "")
    import cards_market as CM
    for k, ln in enumerate(CM._wrap(fig, ft, 12.5, "normal", W - 1.5, 3)):
        fig.text(fx(0.75), fy(H - 0.85 + 0.28 * k), ln, color=MUTED, fontsize=12.5, va="center")
    T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
    T.save(fig, out_path)
