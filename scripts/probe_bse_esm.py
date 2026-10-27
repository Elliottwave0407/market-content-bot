"""Read-only: does BSE publish its ESM stage lists as circulars/notices reachable through the bse library, and can we get BSE bhavcopy history? Posts nothing."""
import os, sys, json, tempfile, traceback, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from datetime import datetime, timedelta
try:
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        now = datetime.now()
        for kw in ({"subject": "ESM"}, {"subject": "Enhanced Surveillance"}, {"department": "Surveillance"}, {}):
            try:
                r = b.circulars(from_date=now - timedelta(days=12), to_date=now, **kw)
                rows = r.get("Table", r) if isinstance(r, dict) else r
                p("circulars", kw, "rows", len(rows), "keys", sorted(rows[0].keys()) if rows else None)
                hit = [x for x in rows if "esm" in json.dumps(x).lower() or "enhanced surveillance" in json.dumps(x).lower()]
                p("  ESM-like:", len(hit))
                for x in hit[:6]: p("   ", json.dumps(x, default=str)[:330])
                if not kw and rows: p("  sample", json.dumps(rows[0], default=str)[:330]); p("  departments:", collections.Counter(str(x.get("DEPARTMENT") or x.get("department")) for x in rows).most_common(6))
            except Exception as e:
                p("circulars", kw, "error", type(e).__name__, repr(e)[:100])
        for d in (now - timedelta(days=1), now - timedelta(days=400)):
            try:
                f = b.bhavcopyReport(d, folder=tempfile.mkdtemp()); p("bhavcopy", d.date(), "ok", f, os.path.getsize(f))
                import zipfile, io, csv
                txt = open(f, encoding="utf-8", errors="ignore").read(600) if not str(f).endswith(".zip") else zipfile.ZipFile(f).read(zipfile.ZipFile(f).namelist()[0])[:600]
                p("   head:", str(txt)[:420].replace("\n", " | "))
            except Exception as e:
                p("bhavcopy", d.date(), "error", type(e).__name__, repr(e)[:100])
        try:
            h = b.equityPriceVolumeT12M("500002"); p("T12M", str(h)[:300])
        except Exception as e:
            p("T12M error", repr(e)[:100])
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
