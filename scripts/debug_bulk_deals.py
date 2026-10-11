import sys
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

def line(r, label):
    if not r:
        return f"  {label}: no data"
    g = {x["item"]: x for x in r["rows"]}
    rev, pat, eps = g["Revenue"], g["Net profit"], g["EPS"]
    return f"  {label} {r['quarter']}: Rev {rf.fmt(rev['cur'])} (QoQ {rev['qoq']}, YoY {rev['yoy']}) | PAT {rf.fmt(pat['cur'])} (QoQ {pat['qoq']}, YoY {pat['yoy']}) | EPS {rf.fmt(eps['cur'], True)} (YoY {eps['yoy']})"

def main():
    day = datetime(2026, 10, 9)
    with BSE(download_folder="./") as bse:
        res = [r for r in day_rows(bse, day) if r.get("CATEGORYNAME") == "Result"]
        for r in res:
            code, name = str(r["SCRIP_CD"]), (r.get("SLONGNAME") or "").strip()
            filed = datetime.fromisoformat(r["DT_TM"][:19])
            out = rf.results_for_filing(bse, code, name, f"{r.get('NEWSSUB')} {r.get('HEADLINE')}", filed)
            p(f"\n{name} ({code}) -> {out['status']} {out.get('quarter')}")
            if out["status"] == "ok":
                p(line(out["consolidated"], "CONS"))
                p(line(out["standalone"], "STD "))
            elif out["status"] == "ok_limited":
                p(line(out["snapshot"], "SNAP"))
        p("\nLOG:", rf.LOG if rf.LOG else "none")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
