"""Diagnostic: how soon after a result announcement does NSE's structured (XBRL) data exist? Samples companies that filed on XBRL_DAY."""
import os, sys, json, time, re
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
day = datetime.strptime(os.environ.get("XBRL_DAY") or datetime.now(nse.IST).strftime("%Y-%m-%d"), "%Y-%m-%d").replace(tzinfo=nse.IST)
rows = nse.result_rows(nse.fetch_day(day))
p("result announcements on the day:", len(rows))
if rows: p("sample row keys:", sorted(rows[0].keys())[:30])
n = 0; s = nse.sess(); st = {"ok": 0, "none": 0}
for x in rows[: int(os.environ.get("XBRL_N", "40"))]:
    sym = x["symbol"]
    try:
        r = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=fd.REF_I, timeout=40).json()
    except Exception as e:
        p(sym, "ERR", repr(e)[:60]); nse._S["sess"] = None; s = nse.sess(); continue
    data = (r or {}).get("data", []) if isinstance(r, dict) else []
    fr = [d for d in data if "Financial" in (d.get("type") or "")][:1]
    if not fr:
        st["none"] += 1; p(f"{sym:12} announced={x.get('an_dt') or x.get('sort_date')} | no integrated filing listed"); continue
    d = fr[0]; st["ok"] += 1
    p(f"{sym:12} announced={x.get('an_dt') or x.get('sort_date')} | qe={d.get('qe_Date')} created={d.get('creation_Date')} broadcast={d.get('broadcast_Date') or d.get('broadcastDate')} xbrl={'yes' if d.get('xbrl') not in (None,'None') else 'no'} cons={d.get('consolidated')}")
p(st)
publish()
