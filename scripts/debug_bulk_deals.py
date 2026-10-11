import sys
from bse import BSE
from ci_out import p, publish

def rows(bse, code, name, q, extra=None):
    prm = {"type1": "c", "strtype": f"{q:.2f}", "strscripcd": code, "strscripname": name, "strresultType": "", "action": "show"}
    if extra:
        prm.update(extra)
    r = bse.session.get(f"{bse.api_url}/Corp_BSEDnBResults_SEBI_Consolidated_Res_ng/w", params=prm, timeout=30)
    d = r.json()
    return [(" ".join(str(x.get("Description")).split()), x.get("Amount"), x.get("RowType")) for x in d]

def main():
    with BSE(download_folder="./") as bse:
        short = rows(bse, "500696", "HUL", 130)
        full = rows(bse, "500820", "ASIANPAINT", 130)
        p("HUL rows", len(short), "ASIAN rows", len(full))
        sd = {x[0] for x in short}
        p("In ASIAN-style full list but NOT in HUL response:", [x[0] for x in full if x[0] not in sd])
        p("HUL response descriptions with RowType:", [(a, c) for a, b, c in short])
        for q in (129, 128, 127):
            r = rows(bse, "500696", "HUL", q)
            p(f"HUL q{q}: rows {len(r)} has_eps {any('Basic EPS' in x[0] for x in r)}")
        p("HUL with resultType 'U':", len(rows(bse, "500696", "HUL", 130, {"strresultType": "U"})))
        p("HUL with resultType 'A':", len(rows(bse, "500696", "HUL", 130, {"strresultType": "A"})))
        p("HUL with action blank:", len(rows(bse, "500696", "HUL", 130, {"action": ""})))

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
