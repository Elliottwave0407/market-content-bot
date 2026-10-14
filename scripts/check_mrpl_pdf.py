"""One-off: what does the MRPL Sep-26 results PDF actually print for the Jun-26 (previous quarter) revenue?"""
import os, re, io, sys
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from datetime import datetime
import requests
from bse import BSE
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
day = datetime(2026, 10, 14)
rec = None
with BSE(download_folder="./") as bse:
    pg = 1
    while pg <= 40 and not rec:
        d = bse.announcements(page_no=pg, from_date=day, to_date=day)
        t = d.get("Table", [])
        if not t:
            break
        for r in t:
            if str(r.get("SCRIP_CD")) == "500109" and (r.get("CATEGORYNAME") or "").lower() == "result":
                rec = r; break
        pg += 1
p("record found:", bool(rec))
if rec:
    att = rec["ATTACHMENTNAME"]
    for folder in ("AttachLive", "AttachHis"):
        r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{att}", headers=UA, timeout=60)
        if r.content[:4] == b"%PDF":
            break
    p("pdf bytes:", len(r.content))
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(r.content))
    p("pages:", len(rd.pages))
    txt = "\n".join((pg_.extract_text() or "") for pg_ in rd.pages[:4])
    p("text chars:", len(txt))
    for rx in (r"4[0-9],?[0-9]{3}\.[0-9]{2}", r"4[17],?608\.?9[0-9]?", r"3[0-9],?[0-9]{3}\.[0-9]{2}"):
        hits = re.findall(rx, txt)
        p(rx, "->", sorted(set(hits))[:12])
    i = txt.find("Revenue from operations")
    p("context:", re.sub(r"\s+", " ", txt[i:i + 260]) if i >= 0 else "no 'Revenue from operations' text layer")
publish()
