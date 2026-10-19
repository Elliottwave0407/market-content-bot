"""Download a 'Link of Recording' filing PDF and print every URL inside it (no API quota)."""
import os, sys, re, io, json, time
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
URL = os.environ.get("PDF_URL", "").strip()
try:
    t = pdf_text(URL) or ""
    p("chars", len(t)); p(re.sub(r"\s+", " ", t)[:600])
    for u in sorted(set(re.findall(r"https?://[^\s\"<>)]+", t))): p("URL:", u)
except Exception as e:
    p("ERR", type(e).__name__, str(e)[:200])
publish()
