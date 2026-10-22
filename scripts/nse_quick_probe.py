"""Read-only, ~5 min: how late does NSE's public announcements feed show a filing compared with its own stamp? Also tests a cache-busting parameter."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
REF = nr.REF
def get(extra):
    d = datetime.now(IST).strftime("%d-%m-%Y")
    u = f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={d}&to_date={d}{extra}"
    t = time.time()
    r = nr.sess().get(u, headers={"Referer": REF, "Cache-Control": "no-cache"}, timeout=40)
    return (r.json() if r.text.strip() else []), time.time() - t
try:
    seen = {"plain": {}, "bust": {}}
    end = time.time() + 290
    first = True
    while time.time() < end:
        for lab, extra in (("plain", ""), ("bust", f"&_={int(time.time()*1000)}")):
            try:
                rows, dt_ = get(extra)
            except Exception as e:
                p(lab, "ERR", repr(e)[:80]); continue
            now = datetime.now(IST)
            ids = {str(x["seq_id"]) for x in rows}
            for x in rows:
                sid = str(x["seq_id"])
                if sid in seen[lab]: continue
                seen[lab][sid] = now
                if not first:
                    try: an = datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
                    except Exception: an = None
                    lag = round((now - an).total_seconds()) if an else None
                    p(f"[{lab}] NEW {x['symbol']} | {x['desc'][:28]} | an_dt {x['an_dt'][12:]} | first seen {now.strftime('%H:%M:%S')} | lag {lag}s | call {dt_:.1f}s | rows {len(rows)}")
        first = False
        time.sleep(5)
    p("done; plain seen", len(seen["plain"]), "bust seen", len(seen["bust"]))
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
