"""Read-only RCA: for each NSE symbol in SYMS find its result PDF between START and END and run scripts/pdf_url_debug.py on it (row dumps + the reader's verdict). Posts nothing."""
import os, sys, subprocess
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse_results as nr
SYMS = [s.strip().upper() for s in os.environ.get("SYMS", "").split(",") if s.strip()]
d0, d1 = datetime.strptime(os.environ.get("START", "2026-11-10"), "%Y-%m-%d"), datetime.strptime(os.environ.get("END", "2026-11-18"), "%Y-%m-%d")
seen, day = {}, d0
while day <= d1:
    try:
        for x in nr.result_rows(nr.fetch_day(day.replace(tzinfo=nr.IST))):
            if x["symbol"].upper() in SYMS and x["symbol"].upper() not in seen:
                seen[x["symbol"].upper()] = x
    except Exception as e:
        print("day", day.date(), "failed", repr(e)[:80])
    day += timedelta(days=1)
for s in SYMS:
    x = seen.get(s)
    if not x:
        print("###### ", s, "no row found"); continue
    url = x.get("attchmntFile") or ""
    print("######", s, x.get("desc") or x.get("sm_name") or "", url, flush=True)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_url_debug.py")], env=dict(os.environ, URL=url, HINT=(x.get("desc") or "")), capture_output=True, text=True, timeout=900)
    print((r.stdout + r.stderr)[-7000:], flush=True)
