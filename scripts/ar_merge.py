"""Merge the NSE and BSE annual report lists: one record per company (ISIN) per financial year (FY = year it ends, e.g. 2025 for 2024-25).
NSE copy preferred when both exist (stable archive link; BSE copy kept as alt). Output store/annual_reports/merged.jsonl and summary.json. No network, no AI."""
import os, sys, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
D = os.path.join(store.ROOT, "annual_reports")
def rd(f):
    out = []
    if os.path.exists(f):
        for l in open(f, encoding="utf-8"):
            try: out.append(json.loads(l))
            except Exception: pass
    return out
nse, bse = rd(os.path.join(D, "nse_ar.jsonl")), rd(os.path.join(D, "bse_ar.jsonl"))
m = json.load(open(os.path.join(store.ROOT, "mcap", "mcap.json")))
code2isin = {str(v.get("s")): k for k, v in m.items() if v.get("s")}
sym2isin = {str(v.get("n")).upper(): k for k, v in m.items() if v.get("n")}
def norm(n): return re.sub(r"[^a-z0-9]", "", re.sub(r"\b(limited|ltd|the)\b", "", (n or "").lower()))
name2isin = {norm(v.get("n")): k for k, v in m.items() if v.get("n")}
RX = re.compile(r"(20\d\d)\s*[-–/]\s*(?:20)?(\d\d)")
def bse_fy(r):
    mm = RX.search((r.get("head") or ""))
    if mm:
        try:
            a, b = int(mm.group(1)), int(mm.group(2))
            if b == (a + 1) % 100: return a + 1
        except Exception: pass
    y, mo = int((r.get("dt") or "2000")[:4]), int((r.get("dt") or "2000-01")[5:7] or 1)
    return y if mo >= 4 else y - 1
rec = {}
for r in nse:
    isin = r.get("isin") or sym2isin.get((r.get("symbol") or "").upper())
    try: fy = int(r.get("toYr"))
    except Exception: continue
    key = (isin or "SYM:" + (r.get("symbol") or ""), fy)
    rec.setdefault(key, {"isin": isin, "name": r.get("name"), "fy": fy, "nse_symbol": r.get("symbol"), "bse_code": None, "dt": r.get("dt"), "url": r.get("url"), "alt": [], "src": ["nse"]})
noiso = 0
for r in bse:
    isin = code2isin.get(str(r.get("code"))) or name2isin.get(norm(r.get("name")))
    fy = bse_fy(r)
    if fy < 2024: continue
    if not isin: noiso += 1
    key = (isin or "BSE:" + str(r.get("code")), fy)
    if key in rec:
        x = rec[key]; x["bse_code"] = str(r.get("code")); x["alt"].append(r["url"]); x["src"].append("bse")
    else:
        rec[key] = {"isin": isin, "name": r.get("name"), "fy": fy, "nse_symbol": None, "bse_code": str(r.get("code")), "dt": r.get("dt"), "url": r["url"], "alt": [], "src": ["bse"], "head": r.get("head")}
rows = sorted(rec.values(), key=lambda x: (x["fy"], x["name"] or ""))
open(os.path.join(D, "merged.jsonl"), "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
by = collections.Counter(r["fy"] for r in rows); both = collections.Counter(r["fy"] for r in rows if len(r["src"]) == 2)
comp = {r["isin"] or r["bse_code"] or r["nse_symbol"] for r in rows}
summ = {"records": len(rows), "companies": len(comp), "by_fy": dict(by), "on_both_exchanges": dict(both), "bse_without_isin": noiso, "nse_rows": len(nse), "bse_rows": len(bse)}
json.dump(summ, open(os.path.join(D, "summary.json"), "w"), indent=1)
print(json.dumps(summ))
