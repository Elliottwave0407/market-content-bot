"""Read-only: why is NSE's Havells QuickResults file 0 bytes for us? Try header variants; also check Havells' row and the other result rows' file sizes."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
try:
    rows = nr.fetch_day(datetime.now(IST).replace(tzinfo=None)) or []
    res = nr.result_rows(rows)
    p("result_rows accepted by the NSE route today:", len(res))
    for x in res:
        p("  ", x["symbol"], x["an_dt"], x.get("attFileSize"), x["attchmntFile"].split("/")[-1][:60])
    hv = [x for x in rows if x["symbol"] == "HAVELLS" and x["desc"] == "Outcome of Board Meeting"][0]
    url = hv["attchmntFile"]
    p("HAVELLS row:", json.dumps({k: hv.get(k) for k in ("attchmntText","attFileSize","hasXbrl","csvName","bflag","orgid")}))
    s = nr.sess()
    for lab, kw in (("range", dict(headers={"Range": "bytes=0-"})), ("identity", dict(headers={"Accept-Encoding": "identity"})), ("pdf-accept", dict(headers={"Accept": "application/pdf"})), ("stream", dict(stream=True))):
        try:
            r = s.get(url, timeout=60, **kw)
            n = len(r.content) if not kw.get("stream") else sum(len(c) for c in r.iter_content(65536))
            p("  ", lab, r.status_code, n, dict((k, v) for k, v in r.headers.items() if k.lower() in ("content-length", "content-type", "content-encoding", "last-modified", "age", "server-timing", "x-cache")))
        except Exception as e: p("  ", lab, "ERR", repr(e)[:100])
    r = s.head(url, timeout=40); p("   HEAD", r.status_code, dict(r.headers))
    # other Havells files from today for comparison
    for x in rows:
        if x["symbol"] == "HAVELLS":
            r = s.get(x["attchmntFile"], timeout=60)
            p("   other Havells file", x["desc"], x.get("attFileSize"), "->", len(r.content), x["attchmntFile"].split("/")[-1][:55])
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
