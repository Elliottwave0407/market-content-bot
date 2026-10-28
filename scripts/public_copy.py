"""One-off: copy already-posted private result cards to the FinGod PUBLIC group (copyMessage, Filing button only; no private buttons).
MSGS = 'msgid:SYMBOL,...'. Filing link looked up from NSE announcements for today. Sends only when CONFIRM=yes."""
import os, sys, json, requests
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import nse_results as nse
TOK = os.environ["TELEGRAM_BOT_TOKEN"]; SRC = os.environ["TELEGRAM_CHAT_ID"]; DST = os.environ["TELEGRAM_PUBLIC_GROUP_ID"]
confirm = os.environ.get("CONFIRM", "").lower() == "yes"
try:
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    rows = nse.result_rows(nse.fetch_day(now))
    for item in os.environ.get("MSGS", "").split(","):
        mid, sym = item.split(":"); sym = sym.upper()
        hit = [x for x in rows if x["symbol"].upper() == sym]
        if not hit:
            p("no filing found for", sym); continue
        hit.sort(key=lambda x: str(x.get("sort_date") or ""))
        url = hit[-1]["attchmntFile"]
        p("COPY", sym, "msg", mid, "filing", url.split("/")[-1][:60])
        if confirm:
            r = requests.post(f"https://api.telegram.org/bot{TOK}/copyMessage", data={"chat_id": DST, "from_chat_id": SRC, "message_id": mid,
                "reply_markup": json.dumps({"inline_keyboard": [[{"text": "\U0001F4C4 Filing", "url": url}]]})}, timeout=60).json()
            p("  ok =", r.get("ok"), (r.get("description") or "")[:80])
except Exception:
    import traceback; p("ERROR", traceback.format_exc()[-600:])
publish()
