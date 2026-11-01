import tempfile, collections
from datetime import datetime, timedelta
from bse import BSE
from ci_out import p, publish
with BSE(download_folder=tempfile.mkdtemp()) as b:
    d1 = datetime.now() - timedelta(days=3)
    for cat, sub in (("-1", "-1"), ("Company Update", "-1"), ("Company Update", "Investor Presentation")):
        try:
            r = b.announcements(from_date=d1, to_date=datetime.now(), category=cat, subcategory=sub) if cat != "-1" else b.announcements(from_date=d1, to_date=datetime.now())
            rows = r.get("Table") or r.get("table") or []
            p("cat", cat, "sub", sub, "keys", list(r.keys())[:4], "rows", len(rows))
            if rows:
                p("   sample keys", sorted(rows[0].keys()))
                c = collections.Counter((x.get("CATEGORYNAME"), x.get("SUBCATNAME")) for x in rows); p("   top cats", c.most_common(12))
                pp = [x for x in rows if "presentation" in ((x.get("HEADLINE") or "") + (x.get("SUBCATNAME") or "")).lower()]
                p("   presentation-like rows", len(pp), [(x.get("SLONGNAME"), x.get("HEADLINE", "")[:70], x.get("ATTACHMENTNAME")) for x in pp[:3]])
        except Exception as e: p("cat", cat, sub, "ERR", type(e).__name__, str(e)[:100])
publish()
