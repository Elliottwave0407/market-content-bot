import sys, os, tempfile
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for pg in (1, 2, 3):
        try:
            d = b.announcements(page_no=pg, from_date=datetime(2026, 10, 1), to_date=datetime(2026, 10, 17), scripcode="544783")
        except Exception as e:
            p("error", repr(e)[:100]); break
        t = d.get("Table", [])
        p("page", pg, "rows", len(t))
        for x in t:
            p(x.get("NEWS_DT"), "|", x.get("CATEGORYNAME"), "|", x.get("SUBCATNAME"), "|", (x.get("NEWSSUB") or "")[:90], "| att:", bool(x.get("ATTACHMENTNAME")), "|", (x.get("HEADLINE") or "")[:70].replace("\n", " "))
        for x in t:
            if "Analyst" in (x.get("SUBCATNAME") or ""):
                p("--- keys:", ",".join(k for k in x.keys()))
                p("ATT:", x.get("ATTACHMENTNAME"), "| MORE:", (x.get("MORE") or "")[:700].replace("\n", " "), "| NEWSSUB:", (x.get("NEWSSUB") or "")[:300], "| HEAD:", (x.get("HEADLINE") or "")[:700].replace("\n", " "))
        if not t: break
publish()
