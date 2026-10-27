import os, sys, io, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests, pypdf
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
urls = ["https://nsearchives.nseindia.com/content/circulars/SURV74008.pdf",
        "https://www.bseindia.com/downloads/UploadDocs/Notices/20260629-29/20260629-29.pdf",
        "https://www.bseindia.com/downloads/UploadDocs/Notices/20260706-24/20260706-24.pdf"]
for u in urls:
    try:
        r = requests.get(u, headers=H, timeout=60)
        p("==", u.split("/")[-1], r.status_code, len(r.content))
        t = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(r.content)).pages)
        t = re.sub(r"\s+", " ", t)
        for i in range(0, min(len(t), 3600), 230): p(t[i:i+230])
    except Exception as e:
        p("ERR", u[-20:], repr(e)[:120])
publish()
