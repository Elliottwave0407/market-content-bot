import os, requests, json
from ci_out import p, publish
tok = os.environ["TELEGRAM_BOT_TOKEN"]
r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", params={"timeout": 0}, timeout=30).json()
p("ok:", r.get("ok"), "updates:", len(r.get("result", [])), r.get("description"))
for u in r.get("result", []):
    p("UPDATE", u["update_id"], [k for k in u if k != "update_id"], json.dumps(u.get("callback_query", {}).get("data")))
wh = requests.get(f"https://api.telegram.org/bot{tok}/getWebhookInfo", timeout=30).json()
p("webhook:", json.dumps(wh.get("result", {}))[:300])
publish()
