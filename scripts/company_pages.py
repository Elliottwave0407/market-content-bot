"""Company page builder (v0, 23 Nov 2026). Joins by ISIN. Writes store/company_pages/<ISIN>.json and index.json.
Public data only. Usage: python3 scripts/company_pages.py [N_PILOT]   (default 20 pilot pages; 0 = all)"""
import sys, os, json, glob, collections
sys.path.insert(0, os.path.dirname(__file__))
import verdict_v3_proto as v
import verdict_v3 as v3
R = os.path.join(os.path.dirname(__file__), "..", "store") + "/"
MN = {0: "Mar", 1: "Jun", 2: "Sep", 3: "Dec"}
lab = lambda q: "%s-%02d" % (MN[q % 4], q // 4 % 100)
ident = {}
for l in open(R + "results_if/numbers.jsonl"):
    r = json.loads(l)
    if r.get("isin"): ident.setdefault(r["isin"], {"isin": r["isin"], "sym": r.get("sym"), "name": r.get("name")})
for i, m in v.mc.items():
    d = ident.setdefault(i, {"isin": i, "sym": None, "name": m.get("n")}); d.update(scrip=m.get("s"), mcap_cr=m.get("m"), group=m.get("g"))
# concalls by scrip code or NSE:SYMBOL
cc = collections.defaultdict(list)
for f in sorted(glob.glob(R + "concall_facts/*.jsonl")):
    for l in open(f):
        r = json.loads(l); cc[r.get("code")].append({"day": r.get("day"), "read": bool(r.get("items")), "skip": r.get("skip"), "n_items": len(r.get("items") or [])})
qs = sorted({q for (_, q) in v.D})
latest = max(qs)
tiers = {}
for q in qs:
    if (v.D and any(k[1] == q - 4 for k in v.D)):
        _, F = v.build(q)
        for i, f in F.items():
            t, pl, why = v3.rate(f); tiers[(i, q)] = (t, pl, why)
def page(i):
    d = dict(ident[i]); rows = []
    expect = [q for q in range(latest - 5, latest + 1)]
    held = []
    for q in qs:
        n = v.D.get((i, q))
        if not n: continue
        held.append(q)
        t = tiers.get((i, q), (None, {}, None))
        rows.append({"q": lab(q), "revenue": n["rev"], "ebitda": n["ebitda"], "pat": n["pat"], "margin_pct": round(n["ebitda"] / n["rev"] * 100, 1), "verdict_v3": t[0], "pillars": t[1], "capped_by": t[2] if len(t) > 2 else None})
    calls = cc.get(d.get("scrip")) or cc.get("NSE:" + (d.get("sym") or "")) or []
    d["quarters"] = rows
    d["completeness"] = {"expected": [lab(q) for q in expect], "held": [lab(q) for q in expect if q in held], "missing": [{"q": lab(q), "reason": "not in results store (not filed, not fetched, or filer is half-yearly)"} for q in expect if q not in held], "concalls_found": len(calls), "concalls_read": sum(1 for c in calls if c["read"]), "latest_concall": max([c["day"] for c in calls], default=None)}
    d["note"] = "Verdict v3 is a prototype; peer-relative; not investment advice"
    return d
if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    out = (os.environ.get("PAGES_OUT") or R + "company_pages") + "/"; os.makedirs(out, exist_ok=True)
    full = [i for i in ident if sum(1 for q in qs if (i, q) in v.D) >= 6 and (v.mc.get(i, {}).get("m") or 0) < 5000]
    full.sort(); pick = full[:: max(1, len(full) // n)][:n] if n else full
    idx = []
    for i in pick:
        p = page(i); json.dump(p, open(out + i + ".json", "w"), indent=1)
        idx.append({"isin": i, "sym": p["sym"], "name": p["name"], "held": len(p["completeness"]["held"]), "concalls": p["completeness"]["concalls_found"]})
    json.dump(idx, open(out + "index.json", "w"), indent=1)
    print(len(idx), "pages;", len(full), "companies with 6+ quarters")
