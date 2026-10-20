"""Read-only probe: is the XBRL value scale (rupees / lakhs / crores) different for some filers? Env SYMBOLS."""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
s = nse.sess()
for sym in (os.environ.get("SYMBOLS") or "SHALBY,KROSS,HFCL,INDIANCARD").split(","):
    d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=fd.REF_I, timeout=40).json().get("data", [])
    x = next((r for r in d if "Financial" in (r.get("type") or "") and r.get("xbrl") not in (None, "None")), None)
    if not x: p(sym, "no integrated filing"); continue
    t = s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
    p(sym, x.get("qe_Date"), x.get("consolidated"), "len", len(t))
    for tag in ("ScaleOfFigures", "LevelOfRoundingUsedInFinancialStatements", "DescriptionOfPresentationCurrency", "RevenueFromOperations"):
        for m in list(re.finditer(r"<[A-Za-z0-9\-]+:%s\b([^>]*)>([^<]*)<" % tag, t))[:2]:
            p("   ", tag, m.group(1)[:90].strip(), "=", m.group(2)[:40])
    for m in list(re.finditer(r"<xbrli:unit id=\"([^\"]+)\"", t))[:3]: p("    unit", m.group(1))
    p("    parsed:", fd.parse_xbrl(t))
publish()
