"""Read-only diagnostic: what the quarterly reader extracts from a company's latest result PDF. Env CODE, FROM."""
import os, sys, json, tempfile, time, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
import gemini_read as gr, pdf_card as pc
code = (os.environ.get("CODE") or "544529").split(",")[0].strip()
since = datetime.strptime(os.environ.get("FROM") or os.environ.get("SINCE") or "2026-10-01", "%Y-%m-%d")
try:
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        rows = []
        for t in range(4):
            try: rows = b.announcements(scripcode=code, from_date=since, to_date=datetime.now(), category="Result").get("Table", []); break
            except Exception: time.sleep(5)
        rows = [r for r in rows if r.get("ATTACHMENTNAME")]
        r = sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[-1]
        p(r.get("SLONGNAME"), r.get("NEWS_DT"), r.get("ATTACHMENTNAME"))
        for folder in ("AttachLive", "AttachHis"):
            rr = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{r['ATTACHMENTNAME']}", headers=pc.UA, timeout=45)
            if rr.content[:4] == b"%PDF": break
        out, err = gr.read_pdf(pc.geminikey(), pc.MODEL, rr.content, tries=3, timeout=120)
        p("err", err); p(json.dumps(out)[:3400])
except Exception as e:
    import traceback; p('ERROR', repr(e)); p(traceback.format_exc()[-1500:])
publish()
