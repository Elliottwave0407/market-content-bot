"""Daily market breadth / mood card. Dry run by default (writes out/mood.png); MOOD_SEND=1 sends it to the market group."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import prices, cards_market as cm

SEND = os.environ.get("MOOD_SEND", "0") == "1"
prices.ensure(days_back=430, log=p)
b = prices.breadth(prices.load())
L = b["liquid"]
p(json.dumps(L))
os.makedirs("out", exist_ok=True)
png = "out/mood.png"
cm.render_mood(b, png)
label, _ = cm.mood_of(L.get("above_50"))
from datetime import datetime
d = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
cap = (f"Market breadth - {d}\n{L['adv']:,} stocks up vs {L['dec']:,} down (NSE stocks traded above Rs 1 Cr)\n"
       f"{L['above_20']:.0f}% above 20-day | {L['above_50']:.0f}% above 50-day | {L['above_200']:.0f}% above 200-day average\n"
       f"52-week highs {L['new_high']} | lows {L['new_low']}\nMood: {label}")
tweet = cap + "\n#StockMarketIndia #Nifty"
p("caption:", cap.replace("\n", " / "))
if SEND:
    import market_posts as mp
    mp.SEND = True
    ok = mp.post([(png, cap, tweet)])
    p("sent:", ok)
publish()
