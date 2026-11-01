"""Merge NSE + BSE presentation listings -> store/ppt_listing/merged.jsonl. Key: ISIN (BSE code via mcap 's'), else normalised name. Same company within 7 days = one document (prefer BSE copy), others kept as alt urls."""
import os, sys, json, re, collections
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import store
D = os.path.join(store.ROOT, "ppt_listing")
mc = json.load(open(os.path.join(store.ROOT, "mcap", "mcap.json")))
c2i = {str(v.get("s")): k for k, v in mc.items() if v.get("s")}
def nm(s): return re.sub(r"[^a-z0-9]", "", re.sub(r"\b(limited|ltd|pvt|private|the)\b", "", (s or "").lower()))
def dt(s, f): return datetime.strptime(s[:10], f)
docs = []
for l in open(os.path.join(D, "nse_ppt.jsonl"), encoding="utf-8"):
    r = json.loads(l)
    if not (r.get("url") or "").lower().endswith((".pdf", ".ppt", ".pptx")): continue
    docs.append({"key": r.get("isin") or "N:" + nm(r.get("name")), "isin": r.get("isin"), "name": r.get("name"), "sym": r.get("symbol"), "day": r["day"], "src": "nse", "url": r["url"]})
n2i = {nm(d["name"]): d["isin"] for d in docs if d.get("isin")}
n2i.update({nm(v.get("n")): k for k, v in mc.items() if v.get("n")})
def byname(name):
    n = nm(name)
    if n in n2i: return n2i[n]
    c = [i for k, i in n2i.items() if len(n) >= 8 and (k.startswith(n) or n.startswith(k)) and len(k) >= 8]
    return c[0] if len(set(c)) == 1 else None
nobi = 0
for l in open(os.path.join(D, "bse_ppt.jsonl"), encoding="utf-8"):
    r = json.loads(l); isin = c2i.get(r["code"])
    if not isin: isin = byname(r.get("name"))
    if not isin: nobi += 1
    docs.append({"key": isin or "N:" + nm(r.get("name")), "isin": isin, "name": r.get("name"), "code": r["code"], "day": r["dt"][:10], "src": "bse", "url": r["url"]})
by = collections.defaultdict(list)
for d in docs: by[d["key"]].append(d)
out = []; dup = 0
for k, L in by.items():
    L.sort(key=lambda d: (d["day"], d["src"] != "bse"))
    cur = None
    for d in L:
        if cur and (dt(d["day"], "%Y-%m-%d") - dt(cur["day"], "%Y-%m-%d")).days <= 7:
            dup += 1; cur.setdefault("alts", []).append({"src": d["src"], "url": d["url"]})
            if d["src"] == "bse" and cur["src"] == "nse": cur["alts"].append({"src": "nse", "url": cur["url"]}); cur["url"] = d["url"]; cur["src"] = "bse"; cur["code"] = d.get("code")
            continue
        cur = dict(d); out.append(cur)
open(os.path.join(D, "merged.jsonl"), "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
q = collections.Counter(); 
for x in out:
    y, m = int(x["day"][:4]), int(x["day"][5:7]); fy = y + 1 if m >= 4 else y; qq = (m - 4) % 12 // 3 + 1; q[f"FY{fy%100} Q{qq} (filed)"] += 1
p("NSE filings", sum(d["src"] == "nse" for d in docs), "| BSE filings", sum(d["src"] == "bse" for d in docs), "| BSE without ISIN match", nobi)
p("merged unique documents", len(out), "| duplicates removed", dup, "| companies", len({x['key'] for x in out}), "| both exchanges", sum(1 for x in out if x.get('alts') and {a['src'] for a in x['alts']} | {x['src']} == {'nse','bse'}))
p("by filing quarter:", dict(sorted(q.items())))
publish()
