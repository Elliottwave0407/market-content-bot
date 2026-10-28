"""Read-only: the BSE ESM notice PDF carries the annexure as a hyperlink. Print link targets (annotations) and try to download them; show the sheet layout (no company data beyond counts)."""
import os, sys, io, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests, pypdf
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
try:
    for n in ["20261028-34", "20261027-36"]:
        r = requests.get(f"https://www.bseindia.com/downloads/UploadDocs/Notices/{n}/{n}.pdf", headers=H, timeout=60)
        p(n, r.status_code, len(r.content))
        if r.content[:4] != b"%PDF": continue
        rd = pypdf.PdfReader(io.BytesIO(r.content)); links = []
        for pg in rd.pages:
            for a in (pg.get("/Annots") or []):
                o = a.get_object(); act = o.get("/A")
                if act is not None:
                    u = act.get_object().get("/URI")
                    if u: links.append(str(u))
        raw = re.findall(rb"/URI\s*\(([^)]*)\)", r.content)
        p("links:", links, "| raw:", [x.decode("latin1")[:200] for x in raw][:5])
        for u in links:
            rr = requests.get(u, headers=H, timeout=60)
            p("GET", u[:160], rr.status_code, len(rr.content), rr.content[:4])
            if rr.content[:2] == b"PK":
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(rr.content), data_only=True)
                for ws in wb.worksheets:
                    p("  sheet", ws.title, ws.max_row, ws.max_column)
                    for row in list(ws.iter_rows(values_only=True))[:14]: p("   ", [str(c)[:28] for c in row if c is not None])
except Exception as e: p("ERR", repr(e)[:300])
publish()
