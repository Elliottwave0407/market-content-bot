"""Read-only probe: how do BSE-SME companies announce results (dates, headlines, PDFs)? Env CODES (BSE scrip codes)."""
import os, sys, tempfile, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
codes = [x.strip() for x in (os.environ.get("CODES") or "544641,543895,543943,543378,511634").split(",") if x.strip()]
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for c in codes:
        rows = []
        for a, z in ((datetime(2025, 1, 1), datetime(2025, 12, 31)), (datetime(2026, 1, 1), datetime(2026, 10, 19))):
            for tries in range(3):
                try:
                    d = b.announcements(scripcode=c, from_date=a, to_date=z, category="Result"); rows += d.get("Table", []); break
                except Exception as e: time.sleep(3)
        p(c, "result announcements:", len(rows))
        for r in sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[:14]:
            p("  ", str(r.get("NEWS_DT"))[:10], "|", str(r.get("HEADLINE") or r.get("NEWSSUB"))[:90], "|", str(r.get("SUBCATNAME"))[:25], "|", "PDF" if r.get("ATTACHMENTNAME") else "-", "|", str(r.get("QUARTER_ID") or ""))
publish()
