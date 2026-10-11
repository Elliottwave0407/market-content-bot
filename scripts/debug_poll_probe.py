import sys, json
from datetime import datetime, timedelta
from bse import BSE
from ci_out import p, publish
try:
    with BSE(download_folder="./") as bse:
        for back in (0, 1):
            d = datetime.now() - timedelta(days=back)
            rows, pg = [], 1
            while pg <= 40:
                data = bse.announcements(page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t: break
                rows += t
                if len(rows) >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
                pg += 1
            res = [r for r in rows if r.get("CATEGORYNAME") == "Result"]
            p(f"day -{back}: total {len(rows)} result {len(res)}")
            if res and back == 0 or (res and back == 1):
                p("KEYS:", sorted(res[0].keys()))
                p("SAMPLE:", json.dumps(res[0])[:900])
                for r in res[:4]:
                    p(" -", r.get("SLONGNAME"), "|", (r.get("NEWSSUB") or "")[:110], "|", r.get("NEWS_DT"), "|", r.get("ATTACHMENTNAME"))
except Exception as e:
    p("Caught error:", repr(e)[:300])
publish()
