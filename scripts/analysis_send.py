"""Send the E2E-style report card + research note to the FinGod_Research_Desk group (manual, dry run by default).
Env: TELEGRAM_BOT_TOKEN, TELEGRAM_ANALYSIS_CHAT_ID, SEND (1 = really send), SYM (default E2E)."""
import os, sys, subprocess, re, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM = os.environ.get("SYM", "E2E").upper(); SEND = os.environ.get("SEND") == "1"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", ""); CHAT = os.environ.get("TELEGRAM_ANALYSIS_CHAT_ID", "").strip()
subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_card.py"), SYM, "--final"], check=True)
subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_note.py"), SYM], check=True, stdout=subprocess.DEVNULL)
png = os.path.join(ROOT, "cards", SYM, "card.png"); note = open(os.path.join(ROOT, "cards", SYM, "note.md")).read()
txt = re.sub(r"\*\*(.+?)\*\*", r"\1", note); txt = re.sub(r"(?m)^\*(.+)\*$", r"\1", txt)    # plain text (no Markdown parse errors)
parts, cur = [], ""
for blk in txt.split("\n\n"):
    if len(cur) + len(blk) + 2 > 3900 and cur: parts.append(cur.strip()); cur = ""
    cur += blk + "\n\n"
if cur.strip(): parts.append(cur.strip())
print(f"card {os.path.getsize(png)//1024} KB | note {len(txt)} chars in {len(parts)} message(s) | chat set: {bool(CHAT)} | send: {SEND}")
if not SEND: sys.exit(0)
if not (TOKEN and CHAT): sys.exit("missing TELEGRAM_BOT_TOKEN or TELEGRAM_ANALYSIS_CHAT_ID")
api = f"https://api.telegram.org/bot{TOKEN}"
with open(png, "rb") as f:
    r = requests.post(api + "/sendDocument", data={"chat_id": CHAT, "caption": f"{SYM} · report card (dry run)"}, files={"document": ("card.png", f)}, timeout=60).json()
print("card:", r.get("ok"), (r.get("description") or "")[:80])
for p in parts:
    r = requests.post(api + "/sendMessage", data={"chat_id": CHAT, "text": p, "disable_web_page_preview": "true"}, timeout=30).json()
    print("note part:", r.get("ok"), (r.get("description") or "")[:80])
