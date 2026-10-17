import sys, os, tempfile
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
from bse import BSE
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for pg in (1, 2):
        d = b.announcements(page_no=pg, from_date=datetime(2026, 10, 10), to_date=datetime(2026, 10, 17), scripcode="544783")
        t = d.get("Table", [])
        for x in t:
            p("BSE", x.get("NEWS_DT"), "|", x.get("SUBCATNAME"), "| AV:", x.get("AUDIO_VIDEO_FILE"), "| IP:", x.get("Investor_Presentation"), "| ATT:", x.get("ATTACHMENTNAME"), "| NSURL:", (x.get("NSURL") or "")[:80])
        if not t: break
s = nse.sess()
for dd in ("16-10-2026", "17-10-2026"):
    try:
        r = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": "E2E", "from_date": dd, "to_date": dd}, timeout=30)
        for x in r.json():
            p("NSE", x.get("an_dt"), "|", x.get("desc"), "|", (x.get("attchmntText") or "")[:140].replace("\n", " "), "|", x.get("attchmntFile"))
    except Exception as e:
        p("nse err", repr(e)[:100])
publish()
