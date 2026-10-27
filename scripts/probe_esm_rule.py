import os, sys, io, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests, pypdf
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
try:
    r = requests.get("https://nsearchives.nseindia.com/content/circulars/SURV69315.pdf", headers=H, timeout=60)
    p(r.status_code, len(r.content))
    t = re.sub(r"\s+", " ", " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(r.content)).pages))
    p("chars", len(t))
    for i in range(0, min(len(t), 9000), 230): p(t[i:i+230])
except Exception as e: p("ERR", repr(e)[:200])
publish()
