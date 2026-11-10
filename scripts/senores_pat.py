"""Read-only: for Senores consolidated quarters, pull revenue lines, other income, PAT split (owners / NCI) and EPS from the results XBRL."""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
out = {}
PAT = re.compile(r"<[\w\-]+:(RevenueFromOperations|OtherOperatingRevenues?|Revenue[A-Za-z]*|OtherIncome|Income|ProfitLossForPeriod|ProfitOrLossAttributableToOwnersOfParent|ProfitOrLossAttributableToNonControllingInterests|BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations|DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations|PaidUpValueOfEquityShareCapital|FaceValueOfEquityShareCapital)\s+contextRef=\"([^\"]+)\"[^>]*>([^<]+)<")
seen = set()
for f in ("store/results_if/numbers.jsonl", "store/results_hist/numbers.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r.get("sym") != "SENORES" or r.get("cons") != "Consolidated": continue
        if r["xbrl"] in seen: continue
        seen.add(r["xbrl"])
        try:
            t = s.get(r["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        except Exception as e:
            p(r["to"], "err", repr(e)[:80]); continue
        res = {}
        for m in PAT.finditer(t):
            if m.group(2) in ("OneD", "CurrentQuarter", "DCYMain", "D1") or "OneD" in m.group(2):
                res.setdefault(m.group(1), m.group(3))
        out[r["to"]] = res
        p(r["to"], r.get("filed"), json.dumps(res))
os.makedirs("companydata/senores_q2", exist_ok=True)
json.dump(out, open("companydata/senores_q2/pat.json", "w"), indent=1)
publish()
