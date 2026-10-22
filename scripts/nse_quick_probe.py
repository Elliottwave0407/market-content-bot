"""Read-only: where is Adani Total Gas (ATGL) in NSE's announcements feeds today?"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
REF = nr.REF
def hit(x): return "ADANI TOTAL" in str(x.get("sm_name", "")).upper() or str(x.get("symbol", "")).upper() in ("ATGL", "ADANIGAS")
try:
    d = datetime.now(IST)
    ds = d.strftime("%d-%m-%Y")
    a = nr.fetch_day(d) or []
    p("dated feed rows", len(a), "latest an_dt", max(str(x.get("an_dt")) for x in a) if a else None)
    for x in a:
        if hit(x): p("  dated:", x["symbol"], x["desc"], x["an_dt"], str(x.get("attchmntText"))[:100], x["attchmntFile"].split("/")[-1][:50])
    for lab, u in (("undated", "https://www.nseindia.com/api/corporate-announcements?index=equities"), ("by symbol", "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=ATGL"),
                   ("dated+symbol", f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=ATGL&from_date={ds}&to_date={ds}")):
        r = nr.sess().get(u, headers={"Referer": REF}, timeout=40)
        j = r.json() if r.text.strip() else []
        p(lab, r.status_code, "rows", len(j), "latest", max((str(x.get("an_dt")) for x in j), default=None))
        n = 0
        for x in j:
            if hit(x) and "22-Oct-2026" in str(x.get("an_dt")):
                p("  ", x["symbol"], x["desc"], x["an_dt"], x.get("exchdisstime"), str(x.get("attchmntText"))[:100]); n += 1
        p("  ATGL rows today in", lab, n)
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
