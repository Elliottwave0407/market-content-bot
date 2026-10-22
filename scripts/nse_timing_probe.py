"""Read-only: when does NSE's announcements feed show a result vs BSE's stamp? Env SYM (default HAVELLS), DAY (YYYY-MM-DD, default today IST)."""
import os, sys, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
try:
    IST = timezone(timedelta(hours=5, minutes=30))
    day = datetime.strptime(os.environ["DAY"], "%Y-%m-%d") if os.environ.get("DAY") else datetime.now(IST).replace(tzinfo=None)
    rows = nr.fetch_day(day) or []
    p("rows today", len(rows))
    sym = (os.environ.get("SYM") or "ATGL").upper()
    for r in rows:
        if str(r.get("symbol", "")).upper() == sym:
            p({k: str(r.get(k))[:90] for k in ("symbol", "desc", "an_dt", "attchmntText", "attchmntFile", "exchdisstime") if k in r})
    acc = nr.result_rows([r for r in rows if str(r.get("symbol","")).upper() == sym])
    p("accepted by NSE route for", sym, ":", len(acc))
    res = [r for r in rows if nr.RES_RX.search((r.get("desc") or "") + " " + (r.get("attchmntText") or ""))]
    p("result-like rows", len(res))
    for r in sorted(res, key=lambda r: str(r.get("an_dt")))[-12:]:
        p(str(r.get("symbol")), str(r.get("an_dt")), str(r.get("exchdisstime")), str(r.get("desc"))[:40])
    p("keys", sorted(rows[0].keys()) if rows else None)
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-800:])
publish()
