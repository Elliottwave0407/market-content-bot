"""Send the E2E-style report card + research note to the FinGod_Research_Desk group (manual, dry run by default).
Env: TELEGRAM_BOT_TOKEN, TELEGRAM_ANALYSIS_CHAT_ID, SEND (1 = really send), SYM (default E2E)."""
import os, sys, subprocess, re, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM = os.environ.get("SYM", "E2E").upper(); SEND = os.environ.get("SEND") == "1"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", ""); CHAT = os.environ.get("TELEGRAM_ANALYSIS_CHAT_ID", "").strip()
if os.environ.get("TEST") == "1":     # three sample messages to try the buttons
    sys.path.insert(0, os.path.join(ROOT, "scripts")); import xbuttons as xb
    for i in (1, 2, 3):
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT, "text": f"Button test {i}: E2E Networks Q2 FY27 sample text. Tap a button.", "reply_markup": xb.markup("Button test " + str(i), fix=True)}, timeout=30).json()
        print("test", i, r.get("ok"), (r.get("description") or "")[:80])
    sys.exit(0)
subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_card.py"), SYM, "--final"], check=True)
subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_note.py"), SYM], check=True, stdout=subprocess.DEVNULL)
png = os.path.join(ROOT, "cards", SYM, "card.png"); note = open(os.path.join(ROOT, "cards", SYM, "note.md")).read()
txt = re.sub(r"\*\*(.+?)\*\*", r"\1", note); txt = re.sub(r"(?m)^\*(.+)\*$", r"\1", txt)    # plain text (no Markdown parse errors)
parts, cur = [], ""
for blk in txt.split("\n\n"):
    if len(cur) + len(blk) + 2 > 3900 and cur: parts.append(cur.strip()); cur = ""
    cur += blk + "\n\n"
if cur.strip(): parts.append(cur.strip())
tweet = open(os.path.join(ROOT, "cards", SYM, "tweet.txt")).read()
sys.path.insert(0, os.path.join(ROOT, "scripts")); import xbuttons as xb
print(f"card {os.path.getsize(png)//1024} KB | note {len(txt)} chars in {len(parts)} message(s) | chat set: {bool(CHAT)} | send: {SEND}")
if not SEND: sys.exit(0)
if not (TOKEN and CHAT): sys.exit("missing TELEGRAM_BOT_TOKEN or TELEGRAM_ANALYSIS_CHAT_ID")
api = f"https://api.telegram.org/bot{TOKEN}"
with open(png, "rb") as f:
    r = requests.post(api + "/sendDocument", data={"chat_id": CHAT, "caption": f"{SYM} · report card\n\nTweet draft:\n{tweet}\n\nAttach the card image, then tap Post to X.", "reply_markup": xb.markup(tweet, fix=True)}, files={"document": ("card.png", f)}, timeout=60).json()
print("card:", r.get("ok"), (r.get("description") or "")[:80])
for i, p in enumerate(parts):
    d = {"chat_id": CHAT, "text": p, "disable_web_page_preview": "true"}
    if i == len(parts) - 1: d["reply_markup"] = xb.markup(None, fix=True)     # note buttons: Posted / Skip / Needs fix (no link)
    r = requests.post(api + "/sendMessage", data=d, timeout=30).json()
    print("note part:", r.get("ok"), (r.get("description") or "")[:80])
