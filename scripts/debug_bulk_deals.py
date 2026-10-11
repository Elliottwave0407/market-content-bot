import re
import sys
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://www.bseindia.com/assets/includenew/js/"
KEYS = ["FinanceResult", "GetResult_consolidated", "FINANCE_DRDOWN", "NSTodayResults", "FinancialResultHeader", "Result_Arch", "detailedResult_Transpose", "consolidate_qtrsearch", "ISDETAILED"]
OUT = []

def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)

def publish():
    text = "\n".join(OUT)[:55000]
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::notice title=probe-output::" + text)

def fetch(name):
    return requests.get(BASE + name, headers=UA, timeout=60).text

def main():
    main_js = fetch("main-DYLU4K5H.js")
    chunks = sorted(set(re.findall(r"chunk-[A-Z0-9]+\.js", main_js)))
    files = [("main-DYLU4K5H.js", main_js)] + [(c, fetch(c)) for c in chunks if c != "chunk-SCEKLEXO.js"]
    shown = {k: 0 for k in KEYS}
    for name, js in files:
        counts = {k: len(re.findall(k, js, re.I)) for k in KEYS}
        hit = {k: v for k, v in counts.items() if v}
        if hit:
            p(f"\n{name}: {hit}")
        for k in KEYS:
            for m in re.finditer(k, js, re.I):
                if shown[k] < 2:
                    shown[k] += 1
                    p(f"\n  [{k}] ctx:", js[max(0, m.start() - 250):m.end() + 300].replace("\n", " "))
    p("\nDone.")

try:
    main()
except Exception as e:
    p(f"\nCaught error: {e}")

publish()
sys.exit(0)
