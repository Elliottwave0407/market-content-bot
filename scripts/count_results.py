"""How many Result filings per day on BSE (peak-day sizing)."""
import time
from datetime import datetime, timedelta
from bse import BSE
from ci_out import p, publish
def ann(bse, **kw):
    for i in range(5):
        try: return bse.announcements(**kw)
        except Exception: time.sleep(5 * (i + 1))
    return {}
try:
    with BSE(download_folder="./") as bse:
        days = [datetime(2026, 8, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17)] + [datetime(2026, 7, d) for d in (14, 15, 16, 17, 20, 21, 22, 23, 24, 27, 28, 29, 30, 31)] + [datetime(2026, 10, d) for d in (8, 9, 12)]
        for d in days:
            n, pg, tot, att = 0, 1, 0, 0
            while pg <= 60:
                data = ann(bse, page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t: break
                tot += len(t)
                rr = [r for r in t if r.get("CATEGORYNAME") == "Result"]
                n += len(rr); att += sum(1 for r in rr if r.get("ATTACHMENTNAME"))
                if tot >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
                pg += 1
            p(f"{d:%a %d %b}: result filings {n} (with PDF {att})")
except Exception as e:
    p("err", repr(e)[:200])
publish()
