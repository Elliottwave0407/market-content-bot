import json
import os
import sys
import time
import requests
from ci_out import p, publish

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

def redact(s):
    return str(s).replace(TOKEN, "<token>") if TOKEN else str(s)

def send(chat_id, text):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"non-json status {r.status_code}"}

def send_photo(chat_id, path, caption):
    with open(path, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data={"chat_id": chat_id, "caption": caption[:1024]}, files={"photo": fh}, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"non-json status {r.status_code}"}

def main():
    if not TOKEN:
        p("TELEGRAM_BOT_TOKEN is not set")
        return
    chat_id = json.load(open("config/telegram.json"))["drafts_chat_id"]
    messages = json.load(open(sys.argv[1]))
    sent = 0
    for i, text in enumerate(messages, 1):
        if isinstance(text, dict):
            r = send_photo(chat_id, text["photo"], text.get("caption", ""))
            p(f"photo {i}: ok={r.get('ok')} {redact(r.get('description', ''))}")
            sent += 1 if r.get("ok") else 0
            time.sleep(1.5)
            continue
        if len(text) > 4000:
            p(f"message {i} too long ({len(text)} chars), skipped")
            continue
        r = send(chat_id, text)
        p(f"message {i}: ok={r.get('ok')} {redact(r.get('description', ''))}")
        sent += 1 if r.get("ok") else 0
        time.sleep(1.2)
    p(f"sent {sent}/{len(messages)}")

try:
    main()
except Exception as e:
    p("Caught error:", redact(e))

publish()
sys.exit(0)
