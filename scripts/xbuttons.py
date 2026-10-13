"""'Post to X' / 'Posted' / 'Skip' buttons for the market group.
- markup(tweet): inline keyboard to put under a card.
- poll(): called from the poll loop; handles button taps (callback queries) and edits the card so everybody sees who posted it."""
import os, json, time, requests
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("MARKET_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
_offset = [0]

def x_url(text):
    return "https://x.com/intent/tweet?text=" + quote(text[:270])

def markup(tweet):
    return json.dumps({"inline_keyboard": [[{"text": "📤 Post to X", "url": x_url(tweet)}],
                                           [{"text": "✅ Posted", "callback_data": "xp"}, {"text": "⏭ Skip", "callback_data": "xs"}]]})

def _call(method, **data):
    try:
        return requests.post(f"{API}/{method}", data=data, timeout=20).json()
    except Exception:
        return {"ok": False}

def poll():
    """Returns list of log lines (empty when nothing happened)."""
    if not TOKEN or not CHAT:
        return []
    r = _call("getUpdates", offset=_offset[0], timeout=0, allowed_updates=json.dumps(["callback_query"]))
    lines = []
    for u in r.get("result", []) or []:
        _offset[0] = max(_offset[0], u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq:
            continue
        msg = cq.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != CHAT:
            continue
        who = (cq.get("from") or {}).get("first_name") or "Someone"
        cap = msg.get("caption") or ""
        done = ("✅ Posted on X by" in cap) or ("⏭ Skipped by" in cap)
        if done or cq.get("data") not in ("xp", "xs"):
            _call("answerCallbackQuery", callback_query_id=cq["id"], text="Already marked." if done else "")
            continue
        stamp = datetime.now(IST).strftime("%d %b, %H:%M")
        tag = f"✅ Posted on X by {who} · {stamp}" if cq["data"] == "xp" else f"⏭ Skipped by {who} · {stamp}"
        new_cap = cap[: 1024 - len(tag) - 3].rstrip() + "\n\n" + tag
        e = _call("editMessageCaption", chat_id=CHAT, message_id=msg["message_id"], caption=new_cap, reply_markup=json.dumps({"inline_keyboard": []}))
        _call("answerCallbackQuery", callback_query_id=cq["id"], text="Marked ✅" if cq["data"] == "xp" else "Skipped")
        lines.append(f"x-button: {tag} (edit ok={e.get('ok')})")
    return lines
