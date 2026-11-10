"""Read-only: for Zen consolidated quarters, pull PAT attributable to owners, NCI share, EPS from the results XBRL."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
out = {}
for f in ("store/results_if/numbers.jsonl", "store/results_hist/numbers.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r.get("sym") != "ZENTEC" or r.get("cons") != "Consolidated": continue
        try:
            t = s.get(r["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        except Exception as e:
            p(r["to"], "err", repr(e)[:80]); continue
        res = {}
        for m in re.finditer(r"<[\w\-]+:(ProfitLossForPeriod|ProfitOrLossAttributableToOwnersOfParent|ProfitOrLossAttributableToNonControllingInterests|BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations|DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations)\s+contextRef=\"([^\"]+)\"[^>]*>([^<]+)<", t):
            if m.group(2) in ("OneD", "CurrentQuarter", "DCYMain", "D1") or "OneD" in m.group(2):
                res.setdefault(m.group(1), m.group(3))
        out[r["to"]] = res
        p(r["to"], json.dumps(res))
os.makedirs("companydata/zen_q2", exist_ok=True)
json.dump(out, open("companydata/zen_q2/pat.json", "w"), indent=1)
publish()
