import os, sys, io, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
try:
    for n in ["20261027-36", "20261026-30"]:
        r = requests.get(f"https://www.bseindia.com/downloads/UploadDocs/Notices/{n}/{n}.pdf", headers=H, timeout=60)
        p(n, r.status_code, len(r.content))
        if r.content[:4] == b"%PDF":
            import pypdf
            rd = pypdf.PdfReader(io.BytesIO(r.content)); p("pages", len(rd.pages))
            t = "\n".join((pg.extract_text() or "") for pg in rd.pages)
            p("chars", len(t)); p(re.sub(r"\s+", " ", t)[:900])
except Exception as e:
    p("ERR", repr(e)[:200])
publish()
