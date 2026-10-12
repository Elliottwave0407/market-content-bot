import json, sys, os, re, requests
from datetime import datetime
from collections import Counter
sys.path.insert(0, "scripts")
from bse import BSE
from ci_out import p, publish
import news_posts as NP
day = datetime(2026, 10, 12)
rows = []
with BSE(download_folder="./") as bse:
    pg = 1
    while pg <= 60:
        d = bse.announcements(page_no=pg, from_date=day, to_date=day)
        t = d.get("Table", [])
        if not t:
            break
        rows += t
        if len(rows) >= (d.get("Table1") or [{}])[0].get("ROWCNT", 0):
            break
        pg += 1
cnt = Counter()
ex = {}
for r in rows:
    tg = NP.classify(r)
    if tg:
        cnt[tg] += 1
        ex.setdefault(tg, []).append(r)
p("total", len(rows), "| would post:", sum(cnt.values()), dict(cnt))
for tg, v in ex.items():
    for r in v[:2]:
        p("SAMPLE", tg, "|", r.get("SLONGNAME"), "|", NP.title_of(r), "| HEADLINE:", (r.get("HEADLINE") or "")[:350].replace("\n", " "), "| MORE:", (r.get("MORE") or "")[:150].replace("\n", " "))
# classification audit: subcats NOT posted among Company Update / Corp action, with counts
miss = Counter((r.get("CATEGORYNAME"), r.get("SUBCATNAME")) for r in rows if not NP.classify(r) and r.get("CATEGORYNAME") not in ("Result", "Board Meeting"))
p("NOT POSTED top:", [(k, v) for k, v in miss.most_common(25)])
for u in ("https://www.rbi.org.in/pressreleases_rss.xml", "https://www.sebi.gov.in/sebirss.xml", "https://www.rbi.org.in/notifications_rss.xml"):
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        p("RSS", u, r.status_code, len(r.text), r.text[:200].replace("\n", " "))
    except Exception as e:
        p("RSS", u, "ERR", repr(e)[:100])
publish()
