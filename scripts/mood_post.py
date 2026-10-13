"""Daily market breadth / mood card. Dry run by default (writes out/mood.png); MOOD_SEND=1 sends it to the market group."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import prices2, cards_market as cm

SEND = os.environ.get("MOOD_SEND", "0") == "1"
prices2.ensure(days_back=430, log=p)
b = prices2.breadth_segments(prices2.load(), prices2.mcaps())
A, S = b["all"], b["seg"]
p(json.dumps(b))
os.makedirs("out", exist_ok=True)
png = "out/mood.png"
cm.render_mood2(b, png)
label, _ = cm.mood_of(A.get("above_50"))
from datetime import datetime
d = datetime.strptime(b["date"], "%Y-%m-%d").strftime("%d %b %Y")
cap = (f"Market breadth - {d} (NSE + BSE, {A['n']:,} stocks counted)\n"
       f"Up {A['adv']:,} | Down {A['dec']:,} | {A['above_50']:.0f}% above 50-day average | Mood: {label}\n"
       + "\n".join(f"{n}: {S[n]['above_50']:.0f}% above 50-day, up {S[n]['adv']:,} / down {S[n]['dec']:,}" for n in ("Large & Mid", "Small", "Micro", "SME")))
tweet = cap + "\n#StockMarketIndia #Nifty"
p("caption:", cap.replace("\n", " / "))
if SEND:
    import market_posts as mp
    mp.SEND = True
    ok = mp.post([(png, cap, tweet)])
    p("sent:", ok)
publish()
