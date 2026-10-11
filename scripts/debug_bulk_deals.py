import sys
from collections import Counter
from datetime import datetime
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

def day_rows(bse, day):
    rows, page = [], 1
    while page <= 40:
        d = bse.announcements(page_no=page, from_date=day, to_date=day)
        part = d.get("Table", []) if isinstance(d, dict) else []
        if not part:
            break
        rows += part
        try:
            total = int(d["Table1"][0]["ROWCNT"])
        except Exception:
            total = None
        if total and len(rows) >= total:
            break
        page += 1
    return rows

def main():
    day = datetime(2026, 10, 9)
    with BSE(download_folder="./") as bse:
        rows = day_rows(bse, day)
        res = [r for r in rows if r.get("CATEGORYNAME") == "Result"]
        p(f"{day:%d-%b-%Y}: total announcements {len(rows)}, Result category {len(res)}")
        p("Result SUBCATNAME counts:", dict(Counter(r.get("SUBCATNAME") for r in res)))
        times = sorted(r.get("DT_TM", "") for r in res)
        p("Result filing time range:", times[:1], times[-1:])
        seen = {}
        for r in res:
            seen.setdefault(str(r["SCRIP_CD"]), r)
        p("distinct companies:", len(seen))
        for code, r in list(seen.items())[:12]:
            p(f"  {code} | {r.get('SLONGNAME')} | {r.get('SUBCATNAME')} | {str(r.get('NEWSSUB'))[:90]} | {r.get('DT_TM')}")
        shown = 0
        for code, r in seen.items():
            if shown >= 6:
                break
            name = (r.get("SLONGNAME") or "").strip()
            c = rf.results(bse, code, name, "consolidated")
            s = rf.results(bse, code, name, "standalone")
            if not (c or s):
                p(f"\n{code} {name}: no data from results endpoints")
                continue
            shown += 1
            p("\n" + rf.render(c))
            p(rf.render(s))
        p("\nLOG:", rf.LOG if rf.LOG else "none")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
