import sys
import json
from bse import BSE

OUT = []
COMPANIES = {"532540": "TCS", "500325": "RELIANCE", "500180": "HDFCBANK", "500112": "SBIN", "500696": "HUL", "500209": "INFY"}

def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)

def publish():
    text = "\n".join(OUT)
    for i in range(0, min(len(text), 36000), 3500):
        chunk = text[i:i + 3500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=probe-output-{i // 3500:02d}::" + chunk)

def get(bse, path, params):
    r = bse.session.get(f"{bse.api_url}/{path}/w", params=params, timeout=30)
    try:
        return r.json()
    except Exception:
        return None

def standalone(bse, code, q):
    d = get(bse, "Corp_detailedResult_Transpose_ng", {"Scrip_cd": code, "Qtr": q})
    rows = d.get("table1", []) if isinstance(d, dict) else []
    out = {}
    for x in rows:
        out.setdefault(x.get("fld_desc"), x.get("Value"))
    return out

def consolidated(bse, code, name, q):
    d = get(bse, "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng", {"type1": "c", "strtype": q, "strscripcd": code, "strscripname": name, "strresultType": "", "action": "show"})
    out = {}
    if isinstance(d, list):
        for x in d:
            out.setdefault(x.get("Description"), x.get("Amount"))
    return out

def pick(d, words):
    return {k: v for k, v in d.items() if k and any(w.lower() in k.lower() for w in words)}

def main():
    keys = ["Date End", "Net Sales", "Revenue", "Net Profit", "Basic", "Interest Earned", "Description"]
    with BSE(download_folder="./") as bse:
        for code, name in COMPANIES.items():
            p(f"\n=== {name} {code}")
            try:
                s = bse.resultsSnapshot(code)
                p("snapshot unit:", s.get("currency_unit"), "periods:", s.get("periods"))
                p("snapshot crores:", json.dumps(s.get("results_in_crores"))[:700])
            except Exception as e:
                p("snapshot error:", e)
            for q in ["131.00", "130.00"]:
                p(f"-- qtr {q} STANDALONE:", json.dumps(pick(standalone(bse, code, q), keys))[:600])
                p(f"-- qtr {q} CONSOLIDATED:", json.dumps(pick(consolidated(bse, code, name, q), keys))[:600])

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
