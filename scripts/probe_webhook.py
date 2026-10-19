import os, sys, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
T = os.environ.get("TELEGRAM_BOT_TOKEN", "")
wh = requests.get(f"https://api.telegram.org/bot{T}/getWebhookInfo", timeout=30).json().get("result", {})
p("pending:", wh.get("pending_update_count"), "| allowed:", wh.get("allowed_updates"), "| url set:", bool(wh.get("url")), "| last_error:", str(wh.get("last_error_message"))[:80])
publish()
