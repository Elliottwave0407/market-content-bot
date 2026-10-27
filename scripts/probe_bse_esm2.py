"""Read-only: open the latest BSE ESM notice (PDF) and print its text, to see how BSE lists stages/entries/exits."""
import os, sys, io, json, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from datetime import datetime, timedelta
import requests
try:
    from bse import BSE
    import pdfplumber
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        now = datetime.now()
        r = b.circulars(from_date=now - timedelta(days=3), to_date=now, subject="ESM")
        rows = r.get("Table", r) if isinstance(r, dict) else r
        x = rows[0]
        p("subject:", x.get("Subject"), "| date", x.get("Notice_Date"), "| No", x.get("Notice_No"), "| dept", x.get("Dept_Name"), "| cat", x.get("category_name"))
        p("PDF_Path:", x.get("PDF_Path"), "| FileName:", x.get("FileName"), "| Attachments:", str(x.get("Attachments"))[:200], "| merge:", str(x.get("merge_Attachments"))[:200])
        cands = []
        for k in ("PDF_Path", "FileName"):
            v = x.get(k)
            if v:
                cands += [v if v.startswith("http") else f"https://www.bseindia.com/markets/downloads/{v}", f"https://www.bseindia.com/downloads/{v}", f"https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page={x.get('Notice_No')}"]
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
        for u in cands[:6]:
            try:
                rr = requests.get(u, headers=H, timeout=40); p("fetch", u[:110], rr.status_code, len(rr.content), rr.content[:5])
                if rr.content[:4] == b"%PDF":
                    with pdfplumber.open(io.BytesIO(rr.content)) as f:
                        t = " ".join((pg.extract_text() or "") for pg in f.pages).replace("\n", " | ")
                    p("PDF pages", len(f.pages), "chars", len(t))
                    for i in range(0, min(len(t), 3600), 800): p(t[i:i + 800])
                    break
            except Exception as e:
                p("fetch error", repr(e)[:80])
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
