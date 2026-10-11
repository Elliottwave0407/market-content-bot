import sys
import json
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

COMPANIES = {"532540": "TCS", "500325": "RELIANCE", "500180": "HDFCBANK", "500696": "HUL", "500820": "ASIANPAINT"}

def main():
    with BSE(download_folder="./") as bse:
        for code, name in COMPANIES.items():
            p(f"\n=== {name} {code}")
            for basis in ("consolidated", "standalone"):
                p(rf.render(rf.results(bse, code, name, basis)))
            try:
                s = bse.resultsSnapshot(code)
                d = {r[0]: r[1:] for r in s["results_in_crores"]["data"]}
                p("check vs BSE snapshot (standalone) revenue/net profit:", d.get("Revenue"), d.get("Net Profit"), "periods", s.get("periods"))
            except Exception as e:
                p("snapshot error:", e)

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
