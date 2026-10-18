import os, sys, re, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
try:
    d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": "E2E"}, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing"}, timeout=40).json()["data"]
    for x in d:
        if "Financial" in (x.get("type") or "") and x.get("consolidated") == "Consolidated" and x.get("qe_Date") == "30-SEP-2026" and x.get("xbrl") not in (None, "None"):
            t = s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
            tags = collections.OrderedDict()
            for m in re.finditer(r"<[A-Za-z0-9\-]+:([A-Za-z0-9]+) ([^>]*contextRef=\"([^\"]+)\"[^>]*)>([^<]+)<", t):
                if re.match(r"^-?[0-9.]+$", m.group(4).strip()):
                    tags.setdefault(m.group(1), []).append((m.group(3), m.group(4).strip()))
            p("distinct numeric tags:", len(tags))
            for k, v in tags.items():
                if re.search(r"Borrow|Cash|Inventor|Receivable|Payable|Equity|Asset|Liabilit|Debt|Capital|Reserves|Property|Depreciation|Finance|Loan|Lease|Invest", k):
                    p(k, v[:3])
            break
    # also what other doc types exist for balance sheet
    d2 = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": "E2E", "period": "Half-Yearly"}, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}, timeout=40).json()
    p("half-yearly legacy rows:", len(d2))
except Exception:
    import traceback; p("ERR", traceback.format_exc()[-700:])
publish()
