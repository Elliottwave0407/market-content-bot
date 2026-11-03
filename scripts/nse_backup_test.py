import os, sys, json
os.environ["NSE_BACKUP"] = "1"
sys.path.insert(0, os.path.dirname(__file__))
import nse_backup as nb
from ci_out import p, publish
rows = json.load(open("store/stub_dry/result.json"))["rows"]
codes = [r["code"] for r in rows if r["kind"] == "stub" and r["status"] == "ok"][:8]
for c in codes:
    r = nb.get(c, "Sep-26", False)
    p(c, "none" if not r else (r["basis"], [q["m"].get("revenue") for q in r["quarters"]], "yprev", bool(r["yprev"])))
publish()
