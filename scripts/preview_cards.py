"""Render SAMPLE cards (invented numbers, marked) to check the look. Usage: python preview_cards.py OUTDIR"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import card, cards_market as cm

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
S = "SAMPLE DATA - preview only"
def m(rev, ebitda, pat, eps):
    return {"revenue": rev * 10, "ebitda": None if ebitda is None else ebitda * 10, "pbt": None, "pat": pat * 10, "eps": eps, "bank": False}
q = [{"q": "Sep-26", "m": m(1250.4, 262.0, 148.2, 9.8)}, {"q": "Jun-26", "m": m(1190.0, 240.5, 131.0, 8.7)},
     {"q": "Mar-26", "m": m(1150.2, 228.0, 120.4, 8.0)}, {"q": "Dec-25", "m": m(1090.0, 210.3, 98.7, 6.5)}, {"q": "Sep-25", "m": m(1010.5, 196.0, 105.9, 7.0)}]
card.render("Sample Industries Ltd", "BSE 500000", "consolidated", q, f"{out}/results_light.png", filed_note=S)
q2 = [dict(x) for x in q]
q2[0] = {"q": "Sep-26", "m": m(88.0, None, -12.5, -1.4)}
q2[1] = {"q": "Jun-26", "m": m(95.0, None, 3.0, 0.3)}
card.render("Loss Making Co Ltd", "BSE 500001", "standalone", q2, f"{out}/results_loss_light.png", filed_note=S)
card.render_stub("Sample Insurance Ltd", "BSE 500002", "Q2 FY27", "BSE has not published structured numbers for this filing", f"{out}/stub_light.png")
deals = [
 {"name": "Awfis Space Solutions", "client": "Peak XV Partners Investments", "side": "S", "qty": 1250000, "price": 412.5, "cr": 51.56, "stake": 1.78, "mcap": 2890, "ex": "N"},
 {"name": "Awfis Space Solutions", "client": "Peak XV Partners Investments", "side": "S", "qty": 380000, "price": 411.9, "cr": 15.65, "stake": 0.54, "mcap": 2890, "ex": "B"},
 {"name": "Jindal Supreme", "client": "Sample Fund A", "side": "B", "qty": 268700, "price": 145.2, "cr": 3.9, "stake": 1.12, "mcap": 350, "ex": "N"},
 {"name": "Paramount Syntex", "client": "Share India Securities", "side": "B", "qty": 4500000, "price": 12.4, "cr": 5.58, "stake": 16.08, "mcap": 35, "ex": "B"},
 {"name": "Anthem Biosciences", "client": "Sample Mutual Fund B", "side": "B", "qty": 800000, "price": 640.0, "cr": 51.2, "stake": 0.53, "mcap": 9650, "ex": "N"},
 {"name": "Tourism Finance Corp", "client": "Sample Trust C", "side": "B", "qty": 1500000, "price": 150.0, "cr": 22.5, "stake": 0.6, "mcap": 3750, "ex": "N"},
 {"name": "Vans Chemistry", "client": "Sample Investor D", "side": "S", "qty": 500000, "price": 38.0, "cr": 1.9, "stake": 3.99, "mcap": None, "ex": "B"},
]
cm.render_deals(deals, "09 Oct 2026", f"{out}/deals_light.png", note=S)
cm.render_fii_dii({"date": "09 Oct 2026", "fii": {"buy": 14250.4, "sell": 16810.2, "net": -2559.8}, "dii": {"buy": 13120.7, "sell": 10480.1, "net": 2640.6},
                   "history": [{"date": "03 Oct", "fii": -1200, "dii": 1800}, {"date": "06 Oct", "fii": 450, "dii": 900}, {"date": "07 Oct", "fii": -3100, "dii": 2900}, {"date": "08 Oct", "fii": -800, "dii": 1500}, {"date": "09 Oct", "fii": -2559.8, "dii": 2640.6}]},
                  f"{out}/fii_dii_light.png", note=S)
cm.render_news({"tag": "ORDER WIN", "company": "Sample Engineering Ltd", "meta": "BSE 500003  |  12 Oct 2026, 16:20 IST",
                "headline": "Sample Engineering receives order worth Rs 245 crore from a state power utility",
                "detail": "The Company has received a Letter of Award for supply and installation of transmission equipment. The order is to be executed within 18 months from the date of the award.", "source": "BSE announcement"},
               f"{out}/news_order_light.png", note=S)
cm.render_news({"tag": "RBI", "company": "Reserve Bank of India", "meta": "Press release  |  12 Oct 2026, 10:30 IST",
                "headline": "RBI announces results of 14-day variable rate repo auction", "detail": None, "source": "RBI press release feed"},
               f"{out}/news_rbi_light.png", note=S)
print("done")
