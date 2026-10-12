import json
from datetime import datetime
from collections import defaultdict
from bse import BSE
from ci_out import p, publish
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
p("total", len(rows))
p("keys:", sorted(rows[0].keys()))
agg = defaultdict(list)
for r in rows:
    agg[(r.get("CATEGORYNAME"), r.get("SUBCATNAME"))].append(r)
for (c, s), v in sorted(agg.items(), key=lambda x: -len(x[1])):
    p(f"{len(v):4d} | {c} | {s} | e.g. {(v[0].get('NEWSSUB') or '')[:110]}")
json.dump(rows, open("news_probe.json", "w"))
# full sample of a few interesting ones
for key in ("Company Update", "Corp. Action"):
    n = 0
    for r in rows:
        if r.get("CATEGORYNAME") == key and n < 2:
            n += 1
            p("SAMPLE", key, json.dumps({k: (str(v)[:300]) for k, v in r.items() if k in ("SLONGNAME","SCRIP_CD","NEWSSUB","HEADLINE","MORE","SUBCATNAME","NEWS_DT","ATTACHMENTNAME","NSURL")}))
publish()
