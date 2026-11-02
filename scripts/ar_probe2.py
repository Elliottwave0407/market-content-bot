"""Read-only probe: how does BSE label annual-report filings in its announcements feed? Tallies category/subcategory names that mention annual report on a busy day."""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime
from ci_out import p, publish
from bse import BSE
cnt = collections.Counter(); ex = {}
with BSE(download_folder="./") as b:
    for day in ("2025-09-05", "2025-09-12"):
        d = datetime.fromisoformat(day); pg = 1; seen = 0
        while pg <= 60:
            try: data = b.announcements(page_no=pg, from_date=d, to_date=d)
            except Exception as e: p("err", day, pg, repr(e)[:80]); break
            t = data.get("Table", [])
            if not t: break
            seen += len(t)
            for r in t:
                txt = ((r.get("HEADLINE") or "") + " " + (r.get("NEWSSUB") or "") + " " + (r.get("SUBCATNAME") or "")).lower()
                if "annual report" in txt:
                    k = (r.get("CATEGORYNAME"), r.get("SUBCATNAME")); cnt[k] += 1
                    ex.setdefault(k, {"name": r.get("SLONGNAME"), "head": (r.get("HEADLINE") or "")[:120], "att": r.get("ATTACHMENTNAME"), "news_dt": r.get("NEWS_DT")})
            if seen >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
            pg += 1
        p(day, "rows seen", seen)
for k, v in cnt.most_common(12): p(k, v, ex[k])
publish()
