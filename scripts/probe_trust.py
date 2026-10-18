import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}
tests = [
    ("shareholding", "https://www.nseindia.com/api/corporate-share-holdings-master", {"index": "equities", "symbol": "E2E"}),
    ("shareholding-ctrl", "https://www.nseindia.com/api/corporate-share-holdings-master", {"index": "equities", "symbol": "RELIANCE"}),
    ("pit-insider", "https://www.nseindia.com/api/corporates-pit", {"index": "equities", "symbol": "E2E", "from_date": "01-04-2026", "to_date": "17-10-2026"}),
    ("pledge", "https://www.nseindia.com/api/corporate-pledgedata", {"index": "equities", "symbol": "E2E"}),
    ("sast", "https://www.nseindia.com/api/corporate-sast-reg29", {"index": "equities", "symbol": "E2E"}),
    ("announce-board", "https://www.nseindia.com/api/corporate-announcements", {"index": "equities", "symbol": "E2E", "from_date": "01-07-2026", "to_date": "17-10-2026"}),
]
for name, url, params in tests:
    try:
        r = s.get(url, params=params, headers=H, timeout=40)
        t = r.text
        try:
            j = r.json()
        except Exception:
            p(name, r.status_code, "not json", t[:100].replace("\n", " ")); continue
        if isinstance(j, list):
            p(name, r.status_code, "list", len(j), "keys:", list(j[0].keys())[:25] if j and isinstance(j[0], dict) else j[:2])
            if j and isinstance(j[0], dict):
                p("  sample:", json.dumps(j[0])[:500])
        elif isinstance(j, dict):
            p(name, r.status_code, "dict keys:", list(j.keys())[:15])
            for k, v in list(j.items())[:2]:
                p("  ", k, json.dumps(v)[:400])
    except Exception as e:
        p(name, "err", repr(e)[:100])
publish()
