"""Read-only probe: how do SME-platform companies file results on NSE? Env SYMBOLS."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
syms = [x.strip().upper() for x in (os.environ.get("SYMBOLS") or "SUNRAKSHAK,BEEZAASAN,GENUSPRIME,KVTOYS,CWD,INVPRECQ").split(",") if x.strip()]
s = nse.sess()
def get(url, params, ref):
    try:
        r = s.get(url, params=params, headers=ref, timeout=40); return r.status_code, r.json()
    except Exception as e: return "ERR", repr(e)[:60]
for sym in syms:
    for idx in ("equities", "sme"):
        for per in ("Quarterly", "Half-Yearly", "Annual"):
            st, d = get("https://www.nseindia.com/api/corporates-financial-results", {"index": idx, "symbol": sym, "period": per}, fd.REF_L)
            n = len(d) if isinstance(d, list) else d
            ex = ""
            if isinstance(d, list) and d:
                x = d[0]; ex = {k: x.get(k) for k in ("toDate", "period", "cumulative", "consolidated", "audited", "xbrl") if k in x}
            p(sym, idx, per, st, n, ex)
        st, d = get("https://www.nseindia.com/api/integrated-filing-results", {"index": idx, "symbol": sym}, fd.REF_I)
        n = len(d.get("data", [])) if isinstance(d, dict) else d
        p(sym, idx, "integrated", st, n)
publish()
