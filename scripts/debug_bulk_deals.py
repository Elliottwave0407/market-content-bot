import sys
import json
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

def main():
    out = {}
    with BSE(download_folder="./") as bse:
        for code, name in [("532540", "TCS"), ("543415", "ANAND RATHI WEALTH")]:
            for basis in ("consolidated",):
                rows = []
                for q in range(131, 126, -1):
                    m = rf.fetch(bse, code, name, basis, q)
                    rows.append({"q": rf.qlabel(q), "m": m})
                out[f"{name}|{basis}"] = rows
    p("JSON:", json.dumps(out))

try:
    main()
except Exception as e:
    p("Caught error:", e)

publish()
sys.exit(0)
