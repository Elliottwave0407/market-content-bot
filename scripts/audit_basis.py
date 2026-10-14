"""Read-only audit: for cards we posted as STANDALONE, does BSE now have consolidated numbers for the same quarter?"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from datetime import datetime
from bse import BSE
import results_fetcher as rf
st = json.load(open("state/seen.json"))
sym = json.load(open("state/symbols.json")).get("m", {})
keys = [k for k in st["posted"] if k.endswith("|standalone")]
p("standalone cards in history:", len(keys), "of", len(st["posted"]))
hits, checked = [], 0
with BSE(download_folder="./") as bse:
    for k in keys[-250:]:
        code, ql, _ = k.split("|")
        try:
            d = datetime.strptime(ql, "%b-%y")
            q = rf.qcode(d.year, d.month)
            m = rf.fetch(bse, code, code, "consolidated", q)
        except Exception as e:
            continue
        checked += 1
        if m and m.get("revenue") is not None:
            hits.append(f"{code} {sym.get(code, '?')} {ql}")
p("checked:", checked, "| consolidated exists now for:", len(hits))
for i in range(0, len(hits), 12):
    p("  " + "; ".join(hits[i:i + 12]))
publish()
