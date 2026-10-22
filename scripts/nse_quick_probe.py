"""Read-only: compare when ATGL / JSL / HAVELLS show up on NSE announcements vs BSE vs structured NSE endpoints."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))
REF = nr.REF
try:
    rows = nr.fetch_day(datetime.now(IST)) or []
    for sym in ("ATGL", "JSL", "HAVELLS"):
        for x in sorted((r for r in rows if r["symbol"] == sym), key=lambda r: r["an_dt"]):
            p("NSE", sym, x["an_dt"][12:], "diss", x.get("exchdisstime", "")[12:], x["desc"][:30], "|", x["attchmntFile"].split("/")[-1][:48])
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for code, nm in (("542066", "ATGL"), ("532508", "JSL"), ("517354", "HAVELLS")):
            try:
                d = b.announcements(page_no=1, scripcode=code, from_date=datetime.now(IST).replace(tzinfo=None), to_date=datetime.now(IST).replace(tzinfo=None))
                for r in d.get("Table", []):
                    p("BSE", nm, "NEWS_DT", str(r.get("NEWS_DT"))[11:19], "DissemDT", str(r.get("DissemDT"))[11:19], "DT_TM", str(r.get("DT_TM"))[11:19], str(r.get("CATEGORYNAME")), str(r.get("HEADLINE"))[:50], "|", r.get("ATTACHMENTNAME"))
            except Exception as e: p("BSE err", nm, repr(e)[:80])
    for lab, u in (("integrated", "https://www.nseindia.com/api/integrated-filing-results?index=equities&period_ended=all&type=Integrated%20Filing-%20Financials"),
                   ("integrated2", "https://www.nseindia.com/api/integrated-filing-results?index=equities"),
                   ("results-today", "https://www.nseindia.com/api/corporates-financial-results-data?index=equities&period=Quarterly"),
                   ("live-analysis", "https://www.nseindia.com/api/home-corporate-announcements?index=equities"),
                   ("latest-ann", "https://www.nseindia.com/api/latest-announcements")):
        try:
            r = nr.sess().get(u, headers={"Referer": REF}, timeout=40)
            t = r.text.strip()
            p(lab, r.status_code, len(t), t[:300].replace("\n", " "))
        except Exception as e: p(lab, "ERR", repr(e)[:80])
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
