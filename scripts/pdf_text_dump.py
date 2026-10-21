"""Diagnostic: print the extracted text of one BSE filing PDF (URL in PDF_URL)."""
import os, sys, io, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from pypdf import PdfReader
u = os.environ["PDF_URL"]
x = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
rd = PdfReader(io.BytesIO(x.content))
p("pages", len(rd.pages), "bytes", len(x.content))
for i, pg in enumerate(rd.pages[:6]):
    t = (pg.extract_text() or "")
    p(f"--- page {i+1} ---")
    for ln in t.splitlines()[:90]:
        p(ln[:160])
publish()
