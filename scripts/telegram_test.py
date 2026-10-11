import os
import sys
import requests
from ci_out import p, publish

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

def redact(s):
    return str(s).replace(TOKEN, "<token>") if TOKEN else str(s)

def api(method, **params):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=params, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"non-json status {r.status_code}"}

def main():
    if not TOKEN:
        p("TELEGRAM_BOT_TOKEN is not set (secret missing or misnamed)")
        return
    p("token length:", len(TOKEN), "| looks like id:token ->", ":" in TOKEN)
    me = api("getMe")
    if not me.get("ok"):
        p("getMe failed:", redact(me.get("description")))
        return
    b = me["result"]
    p(f"bot: @{b.get('username')} id={b.get('id')} can_join_groups={b.get('can_join_groups')} can_read_all_group_messages={b.get('can_read_all_group_messages')}")
    wh = api("getWebhookInfo").get("result", {})
    p("webhook url set:", bool(wh.get("url")), "| pending_update_count:", wh.get("pending_update_count"), "| last_error:", redact(wh.get("last_error_message")))
    up = api("getUpdates", limit=100, timeout=40, allowed_updates=["message", "my_chat_member", "edited_message", "channel_post", "callback_query"])
    if not up.get("ok"):
        p("getUpdates failed:", redact(up.get("description")))
        return
    chats, users = {}, {}
    for u in up.get("result", []):
        for key in ("message", "my_chat_member", "edited_message", "channel_post"):
            m = u.get(key)
            if not m:
                continue
            c = m.get("chat", {})
            chats[c.get("id")] = (c.get("type"), c.get("title") or c.get("first_name"))
            f = m.get("from")
            if f and not f.get("is_bot"):
                users[f.get("id")] = f.get("first_name")
    p("updates seen:", len(up.get("result", [])))
    p("chats:", chats)
    p("human users:", users)
    groups = [cid for cid, (t, _) in chats.items() if t in ("group", "supergroup")]
    if len(groups) == 1:
        r = api("sendMessage", chat_id=groups[0], text="FinGod Drafts bot is connected. This is a test message from GitHub Actions.")
        p("test message sent:", r.get("ok"), redact(r.get("description", "")))
    else:
        p("expected exactly 1 group chat, found:", len(groups), "-> not sending")

try:
    main()
except Exception as e:
    p("Caught error:", redact(e))

publish()
sys.exit(0)
