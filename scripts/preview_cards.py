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
import random
rnd = random.Random(3)
names = ["Anthem Biosciences", "Tourism Finance Corp", "Paramount Syntex", "Jindal Supreme", "Awfis Space Solutions", "Vans Chemistry", "Sample Textiles", "Alpha Engineering", "Beta Pharma", "Gamma Foods", "Delta Infra", "Omega Polymers"]
clients = ["Sample Mutual Fund", "Sample Trust", "Sample Investor", "Sample Securities", "Sample Fund", "Sample Partners"]
deals = []
for i in range(52):
    price = round(rnd.uniform(10, 900), 2)
    qty = rnd.randint(40, 2000) * 1000
    deals.append({"name": names[i % len(names)], "client": f"{clients[i % len(clients)]} {chr(65 + i % 26)}", "side": "B" if i % 5 else "S", "qty": qty, "price": price,
                  "cr": qty * price / 1e7, "stake": None if i % 13 == 0 else round(rnd.uniform(0.1, 6), 2), "mcap": None if i % 13 == 0 else rnd.randint(30, 12000), "ex": "N" if i % 3 else "B"})
paths = cm.render_deals(deals, "09 Oct 2026", f"{out}/deals_light", note=S)
print(paths)
days = ["01 Oct", "03 Oct", "06 Oct", "07 Oct", "08 Oct", "09 Oct"]
mt = []
for dname in days:
    fb, fs, db, ds = rnd.uniform(9000, 16000), rnd.uniform(9000, 16000), rnd.uniform(9000, 16000), rnd.uniform(9000, 16000)
    mt.append({"date": dname, "fii_buy": fb, "fii_sell": fs, "fii_net": fb - fs, "dii_buy": db, "dii_sell": ds, "dii_net": db - ds})
last = mt[-1]
cm.render_fii_dii({"date": "09 Oct 2026", "month": "Oct 2026", "fii": {"buy": last["fii_buy"], "sell": last["fii_sell"], "net": last["fii_net"]}, "dii": {"buy": last["dii_buy"], "sell": last["dii_sell"], "net": last["dii_net"]}, "mtd": mt},
                  f"{out}/fii_dii_light.png", note=S)
cm.render_news({"tag": "ORDER WIN", "company": "Sample Engineering Ltd", "meta": "BSE 500003  |  12 Oct 2026, 16:20 IST",
                "headline": "Sample Engineering receives order worth Rs 245 crore from a state power utility",
                "detail": "The Company has received a Letter of Award for supply and installation of transmission equipment. The order is to be executed within 18 months from the date of the award.", "source": "BSE announcement"},
               f"{out}/news_order_light.png", note=S)
cm.render_news({"tag": "RBI", "company": "Reserve Bank of India", "meta": "Press release  |  12 Oct 2026, 10:30 IST",
                "headline": "RBI announces results of 14-day variable rate repo auction", "detail": None, "source": "RBI press release feed"},
               f"{out}/news_rbi_light.png", note=S)
print("done")
