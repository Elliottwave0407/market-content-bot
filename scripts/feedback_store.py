"""Friends' feedback from the Telegram groups, stored ENCRYPTED in the public repo (hybrid: random Fernet key per item, wrapped with an RSA public key).
Only the holder of the private key can read it. The poller calls ingest(); feedback_read.py (run locally with the private key) decrypts."""
import os, base64, json, requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

DIR = "feedback"
PUB = os.path.join(DIR, "public_key.pem")
LOG = os.path.join(DIR, "inbox.enc")
IMG = os.path.join(DIR, "images2")
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)

def enabled():
    return os.path.exists(PUB)

def _pub():
    return serialization.load_pem_public_key(open(PUB, "rb").read())

def seal(data: bytes) -> bytes:
    k = Fernet.generate_key()
    wrapped = base64.b64encode(_pub().encrypt(k, _OAEP))
    return wrapped + b"." + Fernet(k).encrypt(data)

def unseal(blob: bytes, priv) -> bytes:
    wrapped, token = blob.strip().split(b".", 1)
    k = priv.decrypt(base64.b64decode(wrapped), _OAEP)
    return Fernet(k).decrypt(token)

def ingest(updates, token, chat_labels):
    """updates: raw Telegram updates. chat_labels: {chat_id(str): label}. Returns number of items saved."""
    if not enabled():
        return 0
    api = f"https://api.telegram.org/bot{token}"
    os.makedirs(IMG, exist_ok=True)
    saved = 0
    for u in updates:
        m = u.get("message") or u.get("edited_message")
        if not m:
            continue
        cid = str((m.get("chat") or {}).get("id"))
        if cid not in chat_labels:
            continue
        fr = m.get("from") or {}
        who = fr.get("first_name", "?") + f" [id {fr.get('id')}" + (f" @{fr['username']}" if fr.get("username") else "") + "]"
        txt = m.get("text") or m.get("caption") or ""
        file_id, ext = None, "jpg"
        if m.get("photo"):
            file_id = m["photo"][-1]["file_id"]
        elif m.get("document") and str(m["document"].get("mime_type", "")).startswith("image/"):
            file_id = m["document"]["file_id"]; ext = (m["document"].get("file_name") or "x.png").rsplit(".", 1)[-1]
        elif m.get("document"):
            txt = (txt + " [document: %s]" % m["document"].get("file_name")).strip()
        img = ""
        if file_id:
            try:
                fp = requests.get(api + "/getFile", params={"file_id": file_id}, timeout=60).json()["result"]["file_path"]
                body = requests.get(f"https://api.telegram.org/file/bot{token}/{fp}", timeout=120).content
                name = f"{m.get('date')}_{m.get('message_id')}.{ext}.enc"
                open(os.path.join(IMG, name), "wb").write(seal(body))
                img = f" [image: {name}]"
            except Exception:
                img = " [image: download failed]"
        reply = ""
        rt = m.get("reply_to_message")
        if rt:
            reply = f" (reply to msg {rt.get('message_id')}: {(rt.get('text') or rt.get('caption') or '')[:80]!r})"
        line = f"{m.get('date')} | {chat_labels[cid]} | {who}{' (edited)' if u.get('edited_message') else ''}: {txt}{img}{reply}"
        with open(LOG, "ab") as fh:
            fh.write(seal(line.encode()) + b"\n")
        saved += 1
    return saved
