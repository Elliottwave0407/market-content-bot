"""Build a candlestick chart card for one stock from the cached NSE/BSE daily files. Usage: chart_card.py SYMBOL "Company name" [send]"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import pandas as pd
import prices, prices2, charts

SYMBOL = (sys.argv[1] if len(sys.argv) > 1 else "SKYGOLD").strip().upper()
NAME = sys.argv[2] if len(sys.argv) > 2 else SYMBOL
SEND = len(sys.argv) > 3 and sys.argv[3] == "1"
prices2.ensure(days_back=430, log=p)
# find the ISIN of the symbol in the newest NSE file(s)
isin = None
for f in sorted(glob.glob(os.path.join(prices2.DIR, "*nse.csv.gz")), reverse=True)[:5]:
    d = pd.read_csv(f)
    m = d[d["sym"].astype(str).str.upper() == SYMBOL]
    if len(m):
        isin = m["isin"].iloc[0]; break
p("isin:", isin)
if not isin:
    p("symbol not found in the NSE files")
    publish(); sys.exit(0)
df = prices2.load()
x = df[df["isin"] == isin].copy()
p("rows:", len(x), "from", x["date"].min(), "to", x["date"].max(), "exchange:", x["exch"].iloc[0], "series:", x["series"].iloc[-1])
x = prices.adjusted(x).sort_values("date")
x = x[["date", "open", "high", "low", "close", "vol"]].dropna(subset=["close"])
x["vol"] = x["vol"].fillna(0)
os.makedirs("out", exist_ok=True)
png = f"out/chart_{SYMBOL}.png"
charts.render(x, NAME, SYMBOL, png)
last, prev = x["close"].iloc[-1], x["close"].iloc[-2]
p(f"last close {last:.2f} ({(last / prev - 1) * 100:+.2f}%)")
if SEND:
    import market_posts as mp
    mp.SEND = True
    cap = f"{NAME} (NSE: {SYMBOL}) - daily chart, {pd.to_datetime(x['date'].iloc[-1]).strftime('%d %b %Y')}\nClose ₹{last:,.2f} ({(last / prev - 1) * 100:+.2f}%)\nFor educational purpose only."
    tw = f"{NAME} daily chart: close ₹{last:,.2f} ({(last / prev - 1) * 100:+.2f}%)\n#{SYMBOL} #StockMarketIndia #TechnicalAnalysis"
    p("sent:", mp.post([(png, cap, tw)]))
publish()
