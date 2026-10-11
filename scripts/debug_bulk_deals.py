import sys
from bse import BSE
from ci_out import p, publish

PATHS = ["Corp_FinanceResult_ng", "Corp_GetResult_consolidated_ng", "Corp_Results_ISDETAILED_ng", "Corp_consolidate_qtrsearch_ng", "Corp_Get_BSEDnBresults_New_ng", "Corp_BSEINDIA_CONSILDATERESULT_ng", "Corp_BSEDnB_SplitUP_consoldated_ng", "Corp_Segments_Total_p_ng"]

def sets(code, name):
    return [
        {"Scrip_cd": code, "Qtr": "130.00"},
        {"scripcode": code, "qtr": "130.00"},
        {"Scrip_cd": code, "QuarterID": "130.00"},
        {"strscripcd": code, "strtype": "130.00", "strscripname": name, "type1": "s", "strresultType": "", "action": "show"},
    ]

def main():
    with BSE(download_folder="./") as bse:
        for code, name in [("532540", "TCS"), ("511196", "Can Fin Homes")]:
            p(f"\n##### {name}")
            for path in PATHS:
                for prm in sets(code, name):
                    try:
                        r = bse.session.get(f"{bse.api_url}/{path}/w", params=prm, timeout=30)
                        body = r.text.replace("\n", " ")
                        p(f"{path} {list(prm)[:2]} -> {r.status_code} len {len(body)} | {body[:110]}")
                    except Exception as e:
                        p(f"{path} {list(prm)[:2]} error {str(e)[:60]}")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
