import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
try:
    r = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": "E2E"}, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing"}, timeout=40)
    d = r.json()["data"]; pick = None
    for x in d:
        p(x.get("qe_Date"), x.get("type"), x.get("type_Sub"), x.get("consolidated"), x.get("audited"), (x.get("broadcast_Date") or "")[:11], "xbrl" if x.get("xbrl") not in (None, "None") else "-", (x.get("xbrl") or "")[-50:])
        if not pick and x.get("consolidated") == "Consolidated" and x.get("xbrl") not in (None, "None"): pick = x
    p("PICK", pick and pick["qe_Date"], pick and pick["xbrl"])
    t = s.get(pick["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
    p("len", len(t))
    seen = 0
    for m in re.finditer(r"<([A-Za-z0-9\-]+):([A-Za-z0-9]+) ([^>]*contextRef=\"([^\"]+)\"[^>]*)>([^<]+)<", t):
        if re.match(r"^-?[0-9.]+$", m.group(5).strip()) and seen < 70:
            p(m.group(2), m.group(4), m.group(5).strip()); seen += 1
except Exception:
    import traceback; p("ERR", traceback.format_exc()[-600:])
publish()
