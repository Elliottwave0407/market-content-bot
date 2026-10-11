import sys
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

COMPANIES = {"500696": "HUL", "500820": "ASIANPAINT", "532540": "TCS", "500325": "RELIANCE", "500180": "HDFCBANK"}

def main():
    with BSE(download_folder="./") as bse:
        for code, name in COMPANIES.items():
            p(f"\n=== {name} {code}")
            for basis in ("consolidated", "standalone"):
                p(rf.render(rf.results(bse, code, name, basis)))
        p("\nLOG:", rf.LOG if rf.LOG else "none")
        p("NC = EPS growth not comparable (diverges >8pp from profit growth)")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
