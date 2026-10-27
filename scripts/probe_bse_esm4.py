"""Read-only: find where BSE serves a notice attachment (xlsx) by trying URL patterns on several recent notices; also compares with a notice that has a non-guid attachment name."""
import os, sys, tempfile, traceback, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from datetime import datetime, timedelta
import requests
try:
    from bse import BSE
    H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/markets/MarketInfo/NoticesCirculars.aspx"}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        now = datetime.now()
        r = b.circulars(from_date=now - timedelta(days=4), to_date=now, subject="ESM")
        rows = r.get("Table", r) if isinstance(r, dict) else r
        x = rows[0]; no = x["Notice_No"]; att = x["Attachments"]; pdfp = x["PDF_Path"]; mg = x.get("merge_Attachments")
        p("fields:", {k: str(v)[:90] for k, v in x.items() if k in ("Attachments", "PDF_Path", "FileName", "merge_Attachments", "flag", "Status", "Segment_Name")})
        bases = ["https://www.bseindia.com/downloads/UploadDocs/Notices/", "https://www.bseindia.com/downloads/UploadDocs/", "https://www.bseindia.com/downloads/Notices/", "https://www.bseindia.com/downloads/UploadDocs/Notices/Attachments/",
                 "https://www.bseindia.com/markets/downloads/UploadDocs/Notices/", "https://www.bseindia.com/downloads1/", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/", "https://www.bseindia.com/downloads/UploadDocs/Notices/Annexure/", "https://www.bseindia.com/downloads/UploadDocs/Notices/Attachment/"]
        names = [att, urllib.parse.quote(att, safe=""), f"{no}/{att}", f"{no}/{urllib.parse.quote(att, safe='')}", pdfp, f"{no}/{pdfp}", att.split("$")[0] + ".xlsx", f"{no}/{no}.xlsx", f"{no}/{no}_Annexure.xlsx", f"{no}/Annexure.xlsx"]
        ok = False
        for bs in bases:
            for n in names:
                u = bs + n
                try:
                    rr = requests.get(u, headers=H, timeout=25, allow_redirects=True)
                    if rr.status_code == 200 and rr.content[:2] in (b"PK", b"%P") :
                        p("FOUND", u, len(rr.content), rr.content[:4]); ok = True
                except Exception as e:
                    pass
        p("done; found any:", ok)
        # the HTML page behind the notice number might carry the real link
        pg = requests.get(f"https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page={no}", headers=H, timeout=30)
        p("page text sample:", pg.text[:1200].replace("\n", " ").replace("\r", " "))
except Exception:
    p("ERROR", traceback.format_exc()[-500:])
publish()
