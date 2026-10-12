import sys, json
from datetime import datetime, timedelta
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
try:
    with BSE(download_folder="./") as bse:
        rows = []
        for back in (1, 0):
            d = datetime.now() - timedelta(days=back)
            pg, tot = 1, 0
            while pg <= 40:
                data = bse.announcements(page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t: break
                tot += len(t)
                rows += [r for r in t if r.get("CATEGORYNAME") == "Result"]
                if tot >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
                pg += 1
        p("Result filings (yesterday+today):", len(rows), "| now UTC", datetime.utcnow().strftime("%H:%M"))
        for r in rows[:40]:
            code, name = str(r["SCRIP_CD"]), r["SLONGNAME"]
            head = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat((r.get("NEWS_DT") or "")[:19])
            q = rf.expected_quarter(head, filed)
            st = rf.results_for_filing(bse, code, name, head, filed)
            line = f"{name[:28]} {code} filed {r['NEWS_DT'][5:16]} q={rf.qlabel(q) if q else None} status={st['status']}"
            if st["status"] in ("not_available", "quarter_unverified", "ok_limited") and q:
                raw_s = rf.raw_standalone(bse, code, q)
                raw_c = rf.raw_consolidated(bse, code, name, q)
                line += f" | standalone_rows={len(raw_s or {})} cons_rows={len(raw_c or {})}"
            p(line)
            if st["status"] == "quarter_unverified":
                p("   HEADLINE:", head[:160].replace("\n", " "))
except Exception as e:
    import traceback
    p("Caught error:", repr(e)[:300], traceback.format_exc()[-400:])
publish()
