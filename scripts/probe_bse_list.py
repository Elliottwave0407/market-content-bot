import sys, os, tempfile
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for code in ("544783",):
        for pg in (1, 2):
            try:
                d = b.announcements(page_no=pg, from_date=datetime(2026, 10, 15), to_date=datetime(2026, 10, 17), scripcode=code)
            except Exception as e:
                p("error", repr(e)[:100]); break
            t = d.get("Table", [])
            p("page", pg, "rows", len(t))
            for x in t:
                p(x.get("NEWS_DT"), "|", x.get("CATEGORYNAME"), "|", x.get("SUBCATNAME"), "|", (x.get("NEWSSUB") or "")[:110], "|", (x.get("HEADLINE") or "")[:80])
            if not t: break
publish()
