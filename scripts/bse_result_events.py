"""BSE side of the result-event table. Plain code, no AI, read-only on BSE.
Pulls BSE announcements of category 'Result' day by day from START (default 2024-04-01) and keeps the raw filing rows
(scrip code, name, filing timestamp, headline, quarter code from the headline when it names one) in store/result_events/bse_raw.jsonl.
Resumable: store/result_events/bse_days_done.json remembers finished days. Env: START (YYYY-MM-DD), BUDGET_MIN (default 150), MAX_DAYS (0 = all)."""
import os, sys, json, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_fetcher as rf

OUT = "store/result_events"
RAW = os.path.join(OUT, "bse_raw.jsonl")
DONE = os.path.join(OUT, "bse_days_done.json")
START = datetime.strptime(os.environ.get("START") or "2024-04-01", "%Y-%m-%d")
BUDGET = float(os.environ.get("BUDGET_MIN") or "150")
MAXD = int(os.environ.get("MAX_DAYS") or "0")
T0 = time.time()


def main():
    os.makedirs(OUT, exist_ok=True)
    done = set(json.load(open(DONE))) if os.path.exists(DONE) else set()
    seen = set()
    if os.path.exists(RAW):
        for ln in open(RAW, encoding="utf-8"):
            try:
                seen.add(json.loads(ln)["newsid"])
            except Exception:
                pass
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    d = START
    while d <= today:
        if d.strftime("%Y-%m-%d") not in done or d >= today - timedelta(days=2):
            days.append(d)
        d += timedelta(days=1)
    days.reverse() if os.environ.get("NEWEST_FIRST") == "1" else None
    p("days to fetch:", len(days), "already stored filings:", len(seen))
    n_new = n_days = 0
    with BSE(download_folder="/tmp") as b, open(RAW, "a", encoding="utf-8") as fh:
        for d in days:
            if MAXD and n_days >= MAXD:
                break
            if (time.time() - T0) / 60 > BUDGET:
                p("budget reached"); break
            pg, ok, day_rows = 1, True, 0
            while pg <= 60:
                data = None
                for att in range(3):
                    try:
                        data = b.announcements(page_no=pg, from_date=d, to_date=d, category="Result")
                        break
                    except Exception as e:
                        time.sleep(2 + 3 * att)
                if data is None:
                    ok = False; break
                t = data.get("Table", [])
                if not t:
                    break
                for r in t:
                    nid = str(r.get("NEWSID"))
                    if nid in seen:
                        continue
                    seen.add(nid)
                    head = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
                    try:
                        filed = datetime.fromisoformat((r.get("NEWS_DT") or "")[:19])
                    except Exception:
                        continue
                    qc = None
                    try:
                        qc = rf.expected_quarter(head, filed)
                    except Exception:
                        pass
                    fh.write(json.dumps({"newsid": nid, "code": str(r.get("SCRIP_CD")).strip(), "name": r.get("SLONGNAME"),
                                         "filed": filed.strftime("%Y-%m-%d %H:%M:%S"), "head": head.strip()[:240],
                                         "qcode": qc, "cat": r.get("CATEGORYNAME"), "sub": r.get("SUBCATNAME"),
                                         "att": r.get("ATTACHMENTNAME")}, ensure_ascii=False) + "\n")
                    n_new += 1; day_rows += 1
                pg += 1
            if ok:
                done.add(d.strftime("%Y-%m-%d"))
            n_days += 1
            if n_days % 25 == 0:
                json.dump(sorted(done), open(DONE, "w")); fh.flush()
                p(f"  {n_days} days, {n_new} new filings, last day {d.date()} ({day_rows}), {(time.time() - T0) / 60:.1f} min")
    json.dump(sorted(done), open(DONE, "w"))
    p("finished: days", n_days, "new filings", n_new, "total stored", len(seen), f"{(time.time() - T0) / 60:.1f} min")
    publish()


main()
