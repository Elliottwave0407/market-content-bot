"""Read-only: NSE financial-results feed (corporates-financial-results): do today's filings appear in it, how fast, with what links?"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
REF = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
try:
    for lab, u in (("quarterly", "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly"),
                   ("all", "https://www.nseindia.com/api/corporates-financial-results?index=equities")):
        r = nr.sess().get(u, headers={"Referer": REF}, timeout=60)
        j = r.json() if r.text.strip() else []
        rows = j if isinstance(j, list) else j.get("data", [])
        p(lab, r.status_code, "rows", len(rows))
        today = [x for x in rows if "22-Oct-2026" in str(x.get("broadCastDate")) or "22-Oct-2026" in str(x.get("filingDate"))]
        p("  today rows", len(today))
        for x in sorted(today, key=lambda x: str(x.get("broadCastDate")))[-25:]:
            p("  ", x.get("symbol"), "| broadcast", x.get("broadCastDate"), "| diss", x.get("exchdisstime"), "| filing", x.get("filingDate"), "|", str(x.get("xbrl"))[-50:], "|", str(x.get("resultDetailedDataLink"))[-40:])
        for x in rows:
            if x.get("symbol") in ("ATGL", "JSL") and "2026" in str(x.get("broadCastDate")):
                p("  >>", json.dumps(x)[:700])
        if rows: p("  sample keys", sorted(rows[0].keys()))
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
