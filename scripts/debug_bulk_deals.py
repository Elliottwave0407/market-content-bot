import re
import sys
import json
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://www.bseindia.com/assets/includenew/js/"
PATHS = ["/Corp_FinanceResult_ng/w", "/Corp_GetResult_consolidated_ng/w", "/NSTodayResults_ng/w", "/CorprateResult/w", "/Result_Arch_ng/w", "/FinancialResultHeader/w", "/Corp_Results_ISDETAILED_ng/w"]

def fetch(name):
    return requests.get(BASE + name, headers=UA, timeout=60).text

def js_search():
    main_js = fetch("main-DYLU4K5H.js")
    chunks = sorted(set(re.findall(r"chunk-[A-Z0-9]+\.js", main_js)))
    shown = {k: 0 for k in PATHS}
    for c in ["main-DYLU4K5H.js"] + chunks:
        js = main_js if c.startswith("main") else fetch(c)
        for k in PATHS:
            for m in re.finditer(re.escape(k), js):
                if shown[k] < 1:
                    shown[k] += 1
                    p(f"\n[{k}] in {c}:", js[max(0, m.start() - 420):m.end() + 160].replace("\\n", " "))
    p("\nJS hits:", shown)

def probe(bse):
    for code, name in [("511196", "Can Fin Homes"), ("524000", "Poonawalla Fincorp"), ("544583", "Canara HSBC Life")]:
        for q in (131, 130):
            a = rf.raw_standalone(bse, code, q)
            b = rf._cons_call(bse, code, name, q, "")
            p(f"\n{name} q{q}: standalone rows {len(a)}, consolidated rows {len(b)}; standalone keys: {list(a)[:8]}; cons keys: {list(b)[:8]}")

try:
    with BSE(download_folder="./") as bse:
        probe(bse)
    js_search()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
