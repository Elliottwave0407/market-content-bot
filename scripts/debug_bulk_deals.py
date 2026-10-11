import re
import sys
import json
import requests
from bse import BSE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://www.bseindia.com/assets/includenew/js/"
OUT = []

def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)

def publish():
    text = "\n".join(OUT)[:55000]
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::notice title=probe-output::" + text)

def show(bse, path, params):
    try:
        r = bse.session.get(f"{bse.api_url}/{path}/w", params=params, timeout=30)
        body = r.text
        p(f"\n{path} {params} -> {r.status_code}, {len(body)} chars")
        try:
            d = r.json()
            if isinstance(d, dict):
                p("keys:", {k: (len(v) if isinstance(v, list) else type(v).__name__) for k, v in d.items()})
                for k, v in d.items():
                    if isinstance(v, list) and v:
                        p(f"first rows of {k}:", json.dumps(v[:6])[:1500])
            else:
                p("json:", json.dumps(d)[:800])
        except Exception:
            p("raw:", body[:600])
    except Exception as e:
        p(f"{path} {params} error: {e}")

def main():
    js = requests.get(BASE + "chunk-WRITUV4R.js", headers=UA, timeout=60).text
    i = js.find('case"con":let p={type1')
    p("CON BRANCH:", js[i:i + 900].replace("\n", " "))
    with BSE(download_folder="./") as bse:
        for q in ["131.00", "130.00", "127.00", "126.00"]:
            show(bse, "Corp_detailedResult_Transpose_ng", {"Scrip_cd": "532540", "Qtr": q})

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
