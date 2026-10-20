"""Read-only probe: which XBRL tags do banks / insurers file (current-quarter values)? Env SYMBOLS."""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
s = nse.sess()
for sym in (os.environ.get("SYMBOLS") or "HDFCBANK,SBIN,HDFCLIFE,ICICIGI").split(","):
    got = None
    try:
        d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=fd.REF_I, timeout=40).json().get("data", [])
        for x in d:
            if "Financial" in (x.get("type") or "") and x.get("xbrl") not in (None, "None"):
                got = (x, "integrated"); break
    except Exception as e: p(sym, "integrated failed", repr(e)[:50])
    if not got:
        try:
            l = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": sym, "period": "Quarterly"}, headers=fd.REF_L, timeout=40).json()
            for x in l:
                if x.get("xbrl"): got = (x, "legacy"); break
        except Exception as e: p(sym, "legacy failed", repr(e)[:50])
    if not got: p(sym, "no filing"); continue
    x, src = got
    t = s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
    p(sym, src, x.get("qe_Date") or x.get("toDate"), x.get("consolidated"), "bytes", len(t))
    seen = {}
    for m in re.finditer(r"<[A-Za-z0-9\-]+:([A-Za-z0-9]+)\b([^>]*)>([^<]+)<", t):
        v = m.group(3).strip()
        if re.match(r"^-?[0-9.]+$", v) and "OneD" in m.group(2) and m.group(1) not in seen:
            seen[m.group(1)] = v
    p("  ", " | ".join(f"{k}={v}" for k, v in list(seen.items())[:80]))
publish()
