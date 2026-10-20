"""DRY RUN: lender card from BSE results tables (live data path, finance cost carried). Env CODES (BSE scrip codes; default SBICARD,LICHSGFIN,POONAWALLA)."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
import results_fetcher as rf, card
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym2code = {v: k for k, v in json.load(open(os.path.join(root, "state", "symbols.json")))["m"].items()}
codes = [x.strip() for x in (os.environ.get("CODES") or "").split(",") if x.strip()] or [sym2code[s] for s in ("SBICARD", "LICHSGFIN", "POONAWALLA")]
os.makedirs("out", exist_ok=True)
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for code in codes:
        for basis in ("consolidated", "standalone"):
            q, m = rf.latest(b, code, str(code), basis, start=131)
            if m: break
        if not m: p(code, "no BSE table data"); continue
        qs = [{"q": rf.qlabel(q - i), "m": rf.fetch(b, code, str(code), basis, q - i) or {}} for i in range(5)]
        yprev = rf.fetch(b, code, str(code), basis, q - 5)
        p(code, basis, rf.qlabel(q), "fin carried:", [round(x["m"].get("fin") or 0) for x in qs[:5] if x["m"]])
        r = card.render(str(code), f"BSE {code}", basis, qs, f"out/lender_{code}_{rf.qlabel(q)}.png", yprev=yprev)
        p("  verdict", r, "kind", card.fin_kind(f"BSE {code}"))
publish()
