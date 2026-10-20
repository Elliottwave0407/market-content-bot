"""Read-only: what line items does BSE's results table give for lenders? Env CODES."""
import os, sys, tempfile, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
import results_fetcher as rf
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym2code = {v: k for k, v in json.load(open(os.path.join(root, "state", "symbols.json")))["m"].items()}
codes = [x.strip() for x in (os.environ.get("CODES") or "").split(",") if x.strip()] or [sym2code[s] for s in ("SBICARD", "LICHSGFIN", "POONAWALLA")]
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for code in codes:
        for basis, fn in (("standalone", lambda q: rf.raw_standalone(b, code, q)), ("consolidated", lambda q: rf.raw_consolidated(b, code, str(code), q))):
            raw = fn(130)
            p(code, basis, "keys:", len(raw), "|".join(list(raw)[:40]))
            p("   revenue", rf.first(raw, rf.REV_KEYS), "fin", rf.first(raw, ["Finance Costs"]), "pat", rf.first(raw, ["Net Profit"]))
publish()
