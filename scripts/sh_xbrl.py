"""Read-only: download NSE shareholding XBRL for one symbol's recent quarters and print percent-of-shares per category."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
SYM = os.environ.get("SYMBOL", "SKYGOLD").strip()
rows = json.load(open(f"companydata/_sh/{SYM}.json"))
s = nse.sess()
out = {}
for x in rows[:7]:
    u = x.get("xbrl")
    if not u: continue
    try:
        t = s.get(u, headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
    except Exception as e:
        p(x["date"], "err", repr(e)[:80]); continue
    open(f"companydata/_sh/{SYM}_{x['date']}.xml", "w").write(t)
    res = {}
    for m in re.finditer(r"<[\w\-]+:(ShareholdingAsAPercentageOfTotalNumberOfShares)\s+contextRef=\"([^\"]+)\"[^>]*>([^<]+)<", t):
        res[m.group(2)] = m.group(3)
    out[x["date"]] = res
    p("==", x["date"], len(t), "pct items", len(res))
    for k, v in list(res.items())[:60]: p("  ", k, v)
json.dump(out, open(f"companydata/_sh/{SYM}_pct.json", "w"), indent=1)
publish()
