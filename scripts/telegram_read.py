"""Read the Telegram group and store messages/images ENCRYPTED (repo may be public).
Only prints counts. Decryption key lives in the FEEDBACK_KEY secret and the maintainer's session."""
import os, sys, json, requests
from cryptography.fernet import Fernet

tok = os.environ["TELEGRAM_BOT_TOKEN"]
f = Fernet(os.environ["FEEDBACK_KEY"].encode())
API = f"https://api.telegram.org/bot{tok}"
FILES = f"https://api.telegram.org/file/bot{tok}"
os.makedirs("feedback/images", exist_ok=True)

def safe(e):
    return str(e).replace(tok, "***")

try:
    data = requests.get(API + "/getUpdates", params={"timeout": 0, "allowed_updates": json.dumps(["message", "edited_message"])}, timeout=60).json()
except Exception as e:
    print("error:", safe(e)[:100]); sys.exit(0)

logp = "feedback/messages.enc"
known = set()
if os.path.exists(logp):
    for line in open(logp):
        line = line.strip()
        if line:
            try:
                known.add(f.decrypt(line.encode()).decode())
            except Exception:
                pass
new_lines, imgs = [], 0
for u in data.get("result", []):
    m = u.get("message") or u.get("edited_message")
    if not m:
        continue
    who = (m.get("from") or {}).get("first_name", "?")
    mid = m.get("message_id")
    txt = m.get("text") or m.get("caption") or ""
    file_id, ext = None, "jpg"
    if m.get("photo"):
        file_id = m["photo"][-1]["file_id"]
    elif m.get("document") and str(m["document"].get("mime_type", "")).startswith("image/"):
        file_id = m["document"]["file_id"]
        ext = (m["document"].get("file_name") or "x.png").rsplit(".", 1)[-1]
    elif m.get("document"):
        txt = (txt + " [document: %s]" % m["document"].get("file_name")).strip()
    saved = ""
    if file_id:
        name = f"{m.get('date')}_{mid}.{ext}.enc"
        path = os.path.join("feedback/images", name)
        if not os.path.exists(path):
            try:
                fp = requests.get(API + "/getFile", params={"file_id": file_id}, timeout=60).json()["result"]["file_path"]
                open(path, "wb").write(f.encrypt(requests.get(f"{FILES}/{fp}", timeout=120).content))
                imgs += 1
            except Exception as e:
                print("download failed:", safe(e)[:100]); path = ""
        saved = f" [image: {path}]" if path else ""
    line = f"{m.get('date')} | {who}: {txt}{saved}"
    if line not in known:
        new_lines.append(line)
if new_lines:
    with open(logp, "a") as fh:
        for l in new_lines:
            fh.write(f.encrypt(l.encode()).decode() + "\n")
print(f"new messages saved (encrypted): {len(new_lines)}, new images: {imgs}")
