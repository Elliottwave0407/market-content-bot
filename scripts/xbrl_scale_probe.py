"""Read-only probe: compare parsed revenue per filing/source for a symbol (find scale errors). Env SYMBOLS."""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
s = nse.sess()
def txt(u): return s.get(u, headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
for sym in (os.environ.get("SYMBOLS") or "SHALBY,KROSS").split(","):
    d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=fd.REF_I, timeout=40).json().get("data", [])
    p(sym, "INTEGRATED rows:")
    for x in d:
        if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"): continue
        if (fd._dt(x.get("qe_Date")) or fd.datetime(2000, 1, 1)) < fd.datetime(2025, 3, 1): continue
        t = txt(x["xbrl"]); m = fd.parse_xbrl(t)
        raw = re.search(r"<[A-Za-z0-9\-]+:RevenueFromOperations\b([^>]*)>([^<]+)<", t)
        p("  ", x.get("qe_Date"), x.get("consolidated"), x.get("creation_Date"), "rev", m and m["revenue"], "| raw:", raw and (raw.group(1)[:60].strip(), raw.group(2)))
    l = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": sym, "period": "Quarterly"}, headers=fd.REF_L, timeout=40).json()
    p(sym, "LEGACY rows since 2025:")
    for x in l:
        if not x.get("xbrl") or (fd._dt(x.get("toDate")) or fd.datetime(2000, 1, 1)) < fd.datetime(2025, 3, 1): continue
        t = txt(x["xbrl"]); m = fd.parse_xbrl(t)
        raw = re.search(r"<[A-Za-z0-9\-]+:RevenueFromOperations\b([^>]*)>([^<]+)<", t)
        p("  ", x.get("toDate"), x.get("consolidated"), x.get("cumulative"), x.get("filingDate"), "rev", m and m["revenue"], "| raw:", raw and (raw.group(1)[:60].strip(), raw.group(2)))
publish()
