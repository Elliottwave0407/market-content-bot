import sys
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

def main():
    with BSE(download_folder="./") as bse:
        for code, name, q in [("500325", "RELIANCE", 130), ("500696", "HUL", 130), ("500820", "ASIANPAINT", 129)]:
            for basis in ("consolidated", "standalone"):
                raw = rf.raw_consolidated(bse, code, name, q) if basis == "consolidated" else rf.raw_standalone(bse, code, q)
                p(f"\n=== {name} q{q} {basis}")
                for k, v in raw.items():
                    p(f"{k} = {v}")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
