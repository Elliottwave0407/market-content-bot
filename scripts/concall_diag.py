"""Diagnostic: why do some filed 'transcripts' give no text? Prints pages, characters, size and the first words of each pending filing."""
import os, sys, io, json, glob, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from pypdf import PdfReader
def load(pat):
    out = {}
    for fp in glob.glob(pat):
        for ln in open(fp, encoding="utf-8"):
            try: r = json.loads(ln); out[r["key"]] = r
            except Exception: pass
    return out
f, d = load("store/concall_filings/*.jsonl"), load("store/concalls/*.jsonl")
for k, r in f.items():
    if k in d: continue
    try:
        x = requests.get(r["link"], headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        rd = PdfReader(io.BytesIO(x.content))
        t = " ".join((pg.extract_text() or "") for pg in rd.pages)
        imgs = sum(len(pg.images) for pg in rd.pages[:5])
        p(f"{r['name'][:26]:26} http={x.status_code} kb={len(x.content)//1024} pages={len(rd.pages)} chars={len(t)} imgs(first5)={imgs} | {' '.join(t.split())[:170]!r} | headline={r.get('headline','')[:90]!r}")
    except Exception as e:
        p(f"{r['name'][:26]:26} ERR {repr(e)[:100]}")
publish()
