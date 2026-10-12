import os, requests
from ci_out import p, publish
tok = os.environ["TELEGRAM_BOT_TOKEN"]
r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", params={"timeout": 0}, timeout=30).json()
seen = {}
for u in r.get("result", []):
    for k in ("message", "edited_message", "my_chat_member", "channel_post"):
        m = u.get(k)
        if m and m.get("chat"):
            c = m["chat"]
            seen[c["id"]] = (c.get("title"), c.get("type"))
p("ok:", r.get("ok"), "updates:", len(r.get("result", [])))
for cid, (t, ty) in seen.items():
    p("CHAT", cid, "|", t, "|", ty)
publish()
