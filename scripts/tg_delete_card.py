"""One-off: delete a wrong result card. PRIV_ID = message id in the private chat (deleted directly).
Public group: message ids are not stored, so scan recent ids by forwarding each to the private chat (the reply shows its caption), delete the forwarded copy at once,
and delete the public message when the caption contains MATCH. Never touches a message whose caption does not match. Sends/deletes only when CONFIRM=yes."""
import os, sys, requests, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
TOK = os.environ["TELEGRAM_BOT_TOKEN"]; PRIV = os.environ["TELEGRAM_CHAT_ID"]; PUB = os.environ["TELEGRAM_PUBLIC_GROUP_ID"]
MATCH = os.environ.get("MATCH", "").lower(); PRIV_ID = os.environ.get("PRIV_ID", "").strip(); CONFIRM = os.environ.get("CONFIRM", "").lower() == "yes"
def tg(m, **kw):
    try: return requests.post(f"https://api.telegram.org/bot{TOK}/{m}", data=kw, timeout=30).json()
    except Exception as e: return {"ok": False, "description": type(e).__name__}
def probe(mid):
    r = tg("forwardMessage", chat_id=PRIV, from_chat_id=PUB, message_id=mid)
    if not r.get("ok"): return None, (r.get("description") or "")
    m = r["result"]; tg("deleteMessage", chat_id=PRIV, message_id=m["message_id"])
    return (m.get("caption") or m.get("text") or ""), ""
try:
    if PRIV_ID:
        if CONFIRM:
            r = tg("deleteMessage", chat_id=PRIV, message_id=PRIV_ID); p("private delete ok =", r.get("ok"), (r.get("description") or "")[:60])
        else: p("would delete private", PRIV_ID)
    lo, hi = 1, 1
    while probe(hi)[0] is not None or "not found" not in probe(hi)[1].lower():     # find a high id that does not exist
        hi *= 2
        if hi > 1_000_000: break
    a, b = hi // 2, hi
    while b - a > 1:
        mid = (a + b) // 2
        cap, err = probe(mid)
        if cap is None and "not found" in err.lower(): b = mid
        else: a = mid
    top = a; p("highest public message id about", top)
    found = []
    for mid in range(top, max(0, top - 80), -1):
        cap, err = probe(mid)
        if cap and MATCH in cap.lower():
            found.append(mid); p("MATCH public id", mid, "|", cap.splitlines()[0][:60])
            if CONFIRM:
                r = tg("deleteMessage", chat_id=PUB, message_id=mid); p("  public delete ok =", r.get("ok"), (r.get("description") or "")[:60])
        time.sleep(0.15)
    p("matches:", found, "deleted" if CONFIRM else "dry run")
except Exception:
    import traceback; p("ERROR", traceback.format_exc()[-600:])
publish()
