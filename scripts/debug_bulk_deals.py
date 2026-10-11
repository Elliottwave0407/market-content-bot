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
            text = f"{r.get('NEWSSUB')} {r.get('HEADLINE')}"
            q = rf.expected_quarter(text, filed)
            p(f"\n{name} ({code}) filing says: {str(r.get('NEWSSUB'))[len(name) + 10:][:95]} -> quarter {rf.qlabel(q) if q else 'UNKNOWN'}")
            if q is None:
                p("  -> quarter unverified: link filing only")
                continue
            c = rf.results(bse, code, name, "consolidated", exact=q)
            s = rf.results(bse, code, name, "standalone", exact=q)
            if not (c or s):
                p("  -> BSE data for this quarter not available (yet) or format unsupported")
                try:
                    snap = bse.resultsSnapshot(code)
                    d = {x[0]: x[1:] for x in snap["results_in_crores"]["data"]}
                    p("  snapshot fallback (standalone, Cr):", snap.get("periods"), d.get("Revenue"), d.get("Net Profit"))
                except Exception as e:
                    p("  snapshot fallback failed:", str(e)[:80])
                continue
            p(line(c, "CONS"))
            p(line(s, "STD "))
        p("\nLOG:", rf.LOG if rf.LOG else "none")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
