"""Second audience: copy selected posts (results, FII/DII, bulk/block deals) to the FinGod public group in TELEGRAM_PUBLIC_GROUP_ID.
No buttons here (the group copy only ever gets a Filing link button for result cards, added by the poller). Does nothing when the secret is not set; never raises."""
import os, json, requests

def _ch():
    return os.environ.get("TELEGRAM_PUBLIC_GROUP_ID", "").strip()

def _tok():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

def copy_photo(path, caption, link=None):
    ch = _ch()
    if not ch or not _tok() or not path:
        return None
    try:
        d = {"chat_id": ch, "caption": (caption or "")[:1024]}
        if link:
            d["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "\U0001F4C4 Filing", "url": link}]]})
        with open(path, "rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{_tok()}/sendPhoto", data=d, files={"photo": fh}, timeout=60).json()
        print(f"  channel copy ok={r.get('ok')}", (r.get("description") or "")[:60], flush=True)
        return r
    except Exception as e:
        print("  channel copy failed:", type(e).__name__, flush=True)
        return None

def send_text(text):
    ch = _ch()
    if not ch or not _tok():
        return None
    try:
        return requests.post(f"https://api.telegram.org/bot{_tok()}/sendMessage", json={"chat_id": ch, "text": text[:4000], "disable_web_page_preview": True}, timeout=60).json()
    except Exception as e:
        return {"ok": False, "description": type(e).__name__}

def check():
    """Posts NOTHING. Asks Telegram whether the bot is a member/admin of the group and may post. Returns a dict without the chat id."""
    ch = _ch(); tok = _tok()
    if not ch or not tok:
        return {"configured": False}
    try:
        me = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=30).json().get("result", {})
        cm = requests.get(f"https://api.telegram.org/bot{tok}/getChatMember", params={"chat_id": ch, "user_id": me.get("id")}, timeout=30).json()
        if not cm.get("ok"):
            return {"configured": True, "ok": False, "error": (cm.get("description") or "")[:100]}
        r = cm["result"]
        gc = requests.get(f"https://api.telegram.org/bot{tok}/getChat", params={"chat_id": ch}, timeout=30).json().get("result", {})
        return {"configured": True, "ok": True, "status": r.get("status"), "can_post_messages": r.get("can_post_messages", r.get("status") == "administrator"), "chat_type": gc.get("type"), "title": gc.get("title")}
    except Exception as e:
        return {"configured": True, "ok": False, "error": type(e).__name__}
