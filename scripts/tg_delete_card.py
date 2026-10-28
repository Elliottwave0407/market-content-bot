"""One-off: delete result cards by EXACT message id. PRIV_ID = private chat id, PUB_ID = public group id. No scanning, no forwarding. Deletes only when CONFIRM=yes."""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
TOK = os.environ["TELEGRAM_BOT_TOKEN"]; CONFIRM = os.environ.get("CONFIRM", "").lower() == "yes"
for name, chat, mid in (("private", os.environ.get("TELEGRAM_CHAT_ID", ""), os.environ.get("PRIV_ID", "").strip()), ("public", os.environ.get("TELEGRAM_PUBLIC_GROUP_ID", ""), os.environ.get("PUB_ID", "").strip())):
    if not mid: continue
    if not CONFIRM: p("would delete", name, mid); continue
    try: r = requests.post(f"https://api.telegram.org/bot{TOK}/deleteMessage", data={"chat_id": chat, "message_id": mid}, timeout=30).json()
    except Exception as e: r = {"ok": False, "description": type(e).__name__}
    p(name, "delete ok =", r.get("ok"), (r.get("description") or "")[:60])
publish()
