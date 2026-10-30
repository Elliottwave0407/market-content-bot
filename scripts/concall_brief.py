"""Concall brief per call (free, code only, no AI): arranges the stored VERIFIED facts of each call into one structured page, kept for later quarters.
Output store/concall_briefs/<YYYY-MM>.json = {"<code>|<day>": {...}} for calls on/after FROM (default 2026-10-01).
Every point keeps its quote and its trust grade (A/B/C from store/concall_trust/grades.json). C-grade facts are left out. Cards and posts must use A-grade points only.
Posts nothing. Env: FROM, TO (optional)."""
import os, sys, json, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concall_extract as CE
ROOT = CE.store.ROOT
FROM = os.environ.get("FROM") or "2026-10-01"; TO = os.environ.get("TO") or "9999"
CAPS = [("guidance", 4), ("demand", 3), ("margin", 3), ("order_book", 3), ("capex", 3), ("pricing_cost", 2), ("product_mix", 2), ("fund_raise", 2), ("risk", 3), ("other", 2)]
GR = {"A": 0, "B": 1}
try: grades = json.load(open(os.path.join(ROOT, "concall_trust", "grades.json")))
except Exception: grades = {}
try: sect = json.load(open(os.path.join(ROOT, "sector_map", "sector_map.json")))
except Exception: sect = {}
out = collections.defaultdict(dict)
for f in sorted(glob.glob(os.path.join(ROOT, "concall_facts", "20*.jsonl"))):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("skip") or not r.get("items") or not (FROM <= r["day"] <= TO): continue
        g = (grades.get(r["key"]) or {}).get("g", "")
        pts = []
        for i, it in enumerate(r["items"]):
            gl = g[i] if i < len(g) else "C"
            if gl not in GR: continue
            c = (it.get("cat") or "other").split("|")[0]
            if c not in dict(CAPS): c = "other"
            pts.append({"cat": c, "grade": gl, "statement": it.get("statement"), "value": it.get("value"), "period": it.get("period"), "direction": it.get("direction"), "quote": it.get("quote")})
        sec = {}
        for c, cap in CAPS:
            xs = [x for x in pts if x["cat"] == c]
            xs.sort(key=lambda x: (GR[x["grade"]], 0 if (x["value"] and x["period"]) else 1))
            if xs: sec[c] = xs[:cap]
        n = len(r["items"]); a = g.count("A"); b = g.count("B")
        out[r["day"][:7]][r["key"]] = {"code": r["code"], "name": r["name"], "day": r["day"], "sector": (sect.get(r["code"]) or {}).get("nse_sector") or (sect.get(r["code"]) or {}).get("yf_sector"),
                                       "reader": g and (grades.get(r["key"]) or {}).get("m"), "reread": bool(r.get("reread")),
                                       "coverage": {"facts_read": n, "A": a, "B": b, "C": n - a - b, "shown": sum(len(v) for v in sec.values())}, "src": r.get("src"), "sections": sec}
os.makedirs(os.path.join(ROOT, "concall_briefs"), exist_ok=True)
for m, d in out.items():
    json.dump(d, open(os.path.join(ROOT, "concall_briefs", m + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(m, "briefs", len(d), "points", sum(v["coverage"]["shown"] for v in d.values()), "A-only calls", sum(1 for v in d.values() if v["coverage"]["B"] == 0))
