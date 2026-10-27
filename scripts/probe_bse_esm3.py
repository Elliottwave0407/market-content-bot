"""Read-only: open the Annexure xlsx of the latest BSE ESM notice and print its structure (sheets, headings, first rows)."""
import os, sys, io, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from datetime import datetime, timedelta
import requests
try:
    from bse import BSE
    import openpyxl
    H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        now = datetime.now()
        r = b.circulars(from_date=now - timedelta(days=3), to_date=now, subject="ESM")
        rows = r.get("Table", r) if isinstance(r, dict) else r
        x = rows[0]; no = x["Notice_No"]; att = x.get("Attachments")
        pg = requests.get(f"https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page={no}", headers=H, timeout=40)
        import re
        p("notice page", pg.status_code, len(pg.text), "links:", re.findall(r'(?:href|src)=["\']([^"\']+)', pg.text)[:25])
        base = f"https://www.bseindia.com/downloads/UploadDocs/Notices/{no}/"
        att0 = att.split("$")[0]
        for u in (base + att, base + att0 + ".xlsx", base + no + ".xlsx", base + "Annexure.xlsx", base + "Annexure_ESM.xlsx", f"https://www.bseindia.com/downloads/UploadDocs/Notices/{no}/{x.get('merge_Attachments')}", f"https://www.bseindia.com/markets/downloads/UploadDocs/Notices/{no}/{att}"):
            rr = requests.get(u, headers=H, timeout=40); p("fetch", u[-70:], rr.status_code, len(rr.content), rr.content[:4])
            if rr.content[:2] == b"PK":
                wb = openpyxl.load_workbook(io.BytesIO(rr.content), read_only=True)
                for ws in wb.worksheets:
                    allr = list(ws.iter_rows(values_only=True)); p("sheet", ws.title, "rows", len(allr))
                    for row in allr[:6]: p("   ", [str(c)[:40] for c in row if c is not None])
                break
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
