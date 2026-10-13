"""Run LOCALLY with the private key:  python scripts/feedback_read.py /path/to/feedback_private.pem [n_last]
Prints decrypted feedback lines (and decrypts images into ./feedback_out/)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from cryptography.hazmat.primitives import serialization
import feedback_store as fs
priv = serialization.load_pem_private_key(open(sys.argv[1], "rb").read(), password=None)
n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
lines = [l for l in open(fs.LOG, "rb").read().splitlines() if l.strip()] if os.path.exists(fs.LOG) else []
for l in lines[-n:]:
    try:
        print(fs.unseal(l, priv).decode())
    except Exception as e:
        print("[unreadable line]", repr(e)[:60])
if os.path.isdir(fs.IMG):
    os.makedirs("feedback_out", exist_ok=True)
    for f in sorted(os.listdir(fs.IMG)):
        out = os.path.join("feedback_out", f[:-4])
        if not os.path.exists(out):
            open(out, "wb").write(fs.unseal(open(os.path.join(fs.IMG, f), "rb").read(), priv))
