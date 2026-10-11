import sys
import json
from bse import BSE

OUT = []

def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)

def publish():
    text = "\n".join(OUT)[:55000]
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::notice title=probe-output::" + text)

def get(bse, path, params):
    r = bse.session.get(f"{bse.api_url}/{path}/w", params=params, timeout=30)
    p(f"\n{path} {params} -> {r.status_code}, {len(r.text)} chars")
    try:
        return r.json()
    except Exception:
        p("raw:", r.text[:500])
        return None

def main():
    with BSE(download_folder="./") as bse:
        d = get(bse, "Corp_detailedResult_Transpose_ng", {"Scrip_cd": "532540", "Qtr": "131.00"})
        if d:
            for x in d.get("table1", []):
                p(f"{x.get('fld_type')} | {x.get('fld_desc')} | {x.get('Value')} | hdr={x.get('Header')} | {x.get('type')}")
        for params in [
            {"type1": "c", "strtype": "131.00", "strscripcd": "532540", "strscripname": "TCS", "strresultType": "", "action": "show"},
            {"type1": "c", "strtype": "127.00", "strscripcd": "532540", "strscripname": "TCS", "strresultType": "", "action": "show"},
        ]:
            d = get(bse, "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng", params)
            if isinstance(d, dict):
                p("keys:", {k: (len(v) if isinstance(v, list) else type(v).__name__) for k, v in d.items()})
                for k, v in d.items():
                    if isinstance(v, list) and v:
                        p(f"rows of {k}:", json.dumps(v[:30])[:2500])
            elif d is not None:
                p("json:", json.dumps(d)[:1500])
        h = get(bse, "FinancialResultHeader", {"scripcode": "532540"})
        if h is not None:
            p("header:", json.dumps(h)[:800])

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
