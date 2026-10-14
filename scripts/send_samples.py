"""Send one SAMPLE of every card type (invented numbers, labelled) to the groups: results-type to Results Corner, the rest to the Market group."""
import os, subprocess, sys, time
import requests
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/tmp/samples"
subprocess.run([sys.executable, os.path.join(HERE, "preview_cards.py"), OUT], check=True, stdout=subprocess.DEVNULL)
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
RES = os.environ["TELEGRAM_CHAT_ID"].strip()
MKT = os.environ["TELEGRAM_NEWS_CHAT_ID"].strip()
def send(chat, path, cap):
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data={"chat_id": chat, "caption": cap}, files={"photo": f}, timeout=60).json()
    print(os.path.basename(path), "ok" if r.get("ok") else "FAILED"); time.sleep(3.2)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": RES, "text": "FORMAT REVIEW - sample cards with INVENTED numbers (not real companies). Please comment on layout, fonts, colours, anything to change."}, timeout=30)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": MKT, "text": "FORMAT REVIEW - sample cards with INVENTED numbers (not real companies). Please comment on layout, fonts, colours, anything to change."}, timeout=30)
for f, cap in (("results_light.png", "SAMPLE: result card (profit-making)"), ("results_loss_light.png", "SAMPLE: result card (loss-making)"), ("stub_light.png", "SAMPLE: result without structured numbers")):
    send(RES, f"{OUT}/{f}", cap)
for f, cap in (("fii_dii_light.png", "SAMPLE: FII / DII"), ("deals_light_1.png", "SAMPLE: bulk and block deals (page 1)"), ("deals_light_2.png", "SAMPLE: bulk and block deals (page 2)"),
               ("news_order_light.png", "SAMPLE: order win"), ("news_rating_light.png", "SAMPLE: credit rating"), ("news_mgmt_light.png", "SAMPLE: management change"),
               ("news_corpact_light.png", "SAMPLE: corporate action"), ("news_rbi_light.png", "SAMPLE: RBI / regulator item")):
    send(MKT, f"{OUT}/{f}", cap)
