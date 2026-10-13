import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import xbuttons as xb
p("TOKEN set:", bool(xb.TOKEN), "| CHAT:", xb.CHAT)
r = xb._call("getUpdates", offset=0, timeout=0, allowed_updates=json.dumps(["callback_query"]))
p("getUpdates ->", json.dumps(r)[:400])
import requests
wh = requests.get(f"{xb.API}/getWebhookInfo", timeout=30).json()
p("webhook:", json.dumps(wh.get("result", {}))[:300])
publish()
