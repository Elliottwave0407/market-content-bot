import os, requests
T = os.environ["T"].strip()
text = open("drafts/button_guide.txt", encoding="utf-8").read()
for name in ("A", "B"):
    c = os.environ.get(name, "").strip()
    if not c:
        print(f"::notice::{name} chat id empty"); continue
    r = requests.post(f"https://api.telegram.org/bot{T}/sendMessage", data={"chat_id": c, "text": text}, timeout=30)
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    print(f"::notice::{name} ok={d.get('ok')} {str(d.get('description',''))[:80]}")
