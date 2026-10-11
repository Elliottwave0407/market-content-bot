import sys
import time
from bse import BSE
from ci_out import p, publish

def call(bse, code, name, q):
    r = bse.session.get(f"{bse.api_url}/Corp_BSEDnBResults_SEBI_Consolidated_Res_ng/w", params={"type1": "c", "strtype": f"{q:.2f}", "strscripcd": code, "strscripname": name, "strresultType": "", "action": "show"}, timeout=30)
    try:
        d = r.json()
    except Exception:
        return f"status {r.status_code} non-json len {len(r.text)}"
    rows = [x.get("Description") for x in d] if isinstance(d, list) else []
    return f"status {r.status_code} len {len(r.text)} rows {len(rows)} has_eps {'Basic EPS for continuing operation' in rows} last={rows[-1] if rows else None}"

def main():
    with BSE(download_folder="./") as bse:
        p("-- same session, HUL q130 x6 no sleep")
        for i in range(6):
            p(i, call(bse, "500696", "HUL", 130))
        p("-- alternate companies")
        for code, name in [("500820", "ASIANPAINT"), ("532540", "TCS"), ("500696", "HUL"), ("500325", "RELIANCE"), ("500696", "HUL")]:
            p(name, call(bse, code, name, 130))
        p("-- after 8s sleep")
        time.sleep(8)
        p("HUL", call(bse, "500696", "HUL", 130))
    with BSE(download_folder="./") as bse2:
        p("-- fresh session")
        p("HUL", call(bse2, "500696", "HUL", 130))
        p("ASIANPAINT", call(bse2, "500820", "ASIANPAINT", 130))
        p("-- fresh session, strscripname blank")
        p("HUL blank name", call(bse2, "500696", "", 130))

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
