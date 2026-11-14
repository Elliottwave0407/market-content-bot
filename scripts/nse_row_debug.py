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
    mine = [x for x in rows if str(x.get("symbol", "")).upper() == sym]
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
