"""Read-only: list every NSE announcement row of one symbol for given days, and say which filter would drop it. Posts nothing.
Env: SYM (symbol), DAYS (comma list YYYY-MM-DD)."""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse_results as nr

sym = os.environ["SYM"].upper()
for ds in [d for d in os.environ.get("DAYS", "").split(",") if d]:
    day = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=nr.IST)
    rows = nr.fetch_day(day) or []
    mine = [x for x in rows if sym in str(x.get("symbol", "")).upper() or sym in str(x.get("sm_name", "")).upper() or sym in str(x.get("attchmntText", "")).upper() or sym in str(x.get("attchmntFile", "")).upper()]
    if rows: print("   sample row keys:", sorted(rows[0].keys()), flush=True)
    print(f"== {ds}: {len(rows)} announcements, {len(mine)} for {sym}", flush=True)
    for x in mine:
        desc = (x.get("desc") or "").strip()
        t = x.get("attchmntText") or ""
        f = x.get("attchmntFile") or ""
        why = []
        if desc.lower() not in nr.DESCS: why.append(f"desc '{desc}' not in DESCS")
        if not nr.RES_RX.search(t): why.append("attchmntText has no results words")
        if nr.NOT_RX.search(t): why.append("NOT_RX hit")
        if not f.lower().endswith(".pdf"): why.append("file not .pdf")
        print("  ", x.get("an_dt"), "| desc:", desc, "| file:", f, "| seq:", x.get("seq_id"), "\n     text:", t[:300].replace("\n", " "), "\n     DROPPED BY:", why or "nothing (would be processed)", flush=True)

# the SME board has its own announcements index: check it too
import time
for idx in ("sme", "debt"):
    for ds in [d for d in os.environ.get("DAYS", "").split(",") if d]:
        day = datetime.strptime(ds, "%Y-%m-%d")
        dd = day.strftime("%d-%m-%Y")
        try:
            r = nr.sess().get(f"https://www.nseindia.com/api/corporate-announcements?index={idx}&from_date={dd}&to_date={dd}&_={int(time.time() * 1000)}", headers={"Referer": nr.REF, "Cache-Control": "no-cache"}, timeout=40)
            rows = r.json() if r.status_code == 200 and r.text.strip() else []
        except Exception as e:
            print(f"index={idx} {ds}: error {repr(e)[:100]}", flush=True); continue
        mine = [x for x in rows if sym in str(x.get("symbol", "")).upper() or sym in str(x.get("sm_name", "")).upper() or sym in str(x.get("attchmntText", "")).upper()]
        print(f"INDEX {idx} {ds}: status {r.status_code}, {len(rows)} rows, {len(mine)} for {sym}", flush=True)
        for x in mine:
            print("    ", x.get("an_dt"), "|", x.get("desc"), "|", x.get("attchmntFile"), "|", (x.get("attchmntText") or "")[:200].replace("\n", " "), flush=True)

# 15 Nov: why does the live poller skip these? print seq_id, done-state, BSE code, filters
try:
    import json
    st = json.load(open("state/nse_results.json")); done = set(map(str, st["done"]))
    maps = nr.bse_maps()
    for d_ in os.environ.get("DAYS", "").split(","):
        if not d_.strip(): continue
        day_ = datetime.strptime(d_.strip(), "%Y-%m-%d").replace(tzinfo=nr.IST)
        allr = nr.fetch_day(day_)
        for x in allr:
            if sym.upper() in (x.get("symbol") or "").upper():
                kept = x in nr.result_rows([x])
                print("DBG seq", x.get("seq_id"), "in_done", str(x.get("seq_id")) in done, "kept_by_result_rows", kept, "bse_code", nr.bse_code(x, maps) if maps else None, "fin_sym", nr._fin_sym(x["symbol"]), x.get("desc"), flush=True)
except Exception as e:
    print("DBG error", repr(e)[:200], flush=True)
