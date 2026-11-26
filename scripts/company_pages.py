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
arf = {}
for fn in glob.glob(R + "annual_report_facts/*.json"):
    try: d = json.load(open(fn))
    except Exception: continue
    if d.get("facts"): arf[d["isin"]] = {"fy": d["fy"], **{k: d["facts"].get(k) for k in ("business", "segments", "capacity_or_capex", "guidance_or_targets", "order_book_cr", "auditor", "promoter_holding_pct", "promoter_pledge_pct", "employees", "subsidiaries_count", "key_risks", "dividend_per_share")}}
CL = os.environ.get("CLAIMS_DIR") or "/home/claude/fingod-company-data/claims"
def claims_of(i):
    fn = os.path.join(CL, i + ".json")
    if not os.path.exists(fn): return None
    L = json.load(open(fn))["claims"]; by = collections.Counter(c["cat"] for c in L)
    g = [c for c in L if c["cat"] == "guidance"][-5:]
    return {"total": len(L), "by_category": dict(by), "latest_guidance": [{"day": c["first_day"], "statement": c["statement"], "period": c.get("period")} for c in g], "ledger": "claims/%s.json" % i}
qs = sorted({q for (_, q) in v.D})
latest = max(qs)
import verdict_v21 as v21, verdict_method_bakeoff as bake
tiers = {}
for (i, q), c in v.D.items():
    y, pv = v.D.get((i, q - 4)), v.D.get((i, q - 1))
    if not (y and pv): continue
    yp = v.D.get((i, q - 5))
    try: r_ = v21.rate21(bake.mk(c), bake.mk(pv), bake.mk(y), bake.mk(yp) if yp else None)
    except Exception: continue
    if r_.get("tier"): tiers[(i, q)] = r_
TAX = os.environ.get("TAXONOMY") or "/home/claude/fingod-company-data/taxonomy/business_groups.json"
biz = {}
if os.path.exists(TAX):
    for g in json.load(open(TAX))["groups"]:
        for sg in g["subgroups"]:
            for m in sg["members"]:
                peers = sg["members"] if sg["size"] >= 3 else [x for s2 in g["subgroups"] for x in s2["members"]]
                biz[m["isin"]] = {"group": g["id"], "group_name": g["name"], "subgroup": sg["id"], "subgroup_name": sg["name"], "terms": sg["terms"], "peer_basis": "sub-group" if sg["size"] >= 3 else ("group" if len(peers) >= 3 else "no true peers"), "peers": [x for x in peers if x["isin"] != m["isin"]][:25]}
def page(i):
    d = dict(ident[i]); rows = []
    expect = [q for q in range(latest - 5, latest + 1)]
    held = []
    for q in qs:
        n = v.D.get((i, q))
        if not n: continue
        held.append(q)
        t = tiers.get((i, q)) or {}
        rows.append({"q": lab(q), "revenue": n["rev"], "ebitda": n["ebitda"], "pat": n["pat"], "margin_pct": round(n["ebitda"] / n["rev"] * 100, 1), "verdict": t.get("tier"), "verdict_version": "v2.1" if t else None, "tags": t.get("tags"), "verdict_notes": (t.get("caps") or []) + (t.get("v21_notes") or []) if t else None})
    calls = cc.get(d.get("scrip")) or cc.get("NSE:" + (d.get("sym") or "")) or []
    d["quarters"] = rows
    d["completeness"] = {"expected": [lab(q) for q in expect], "held": [lab(q) for q in expect if q in held], "missing": [{"q": lab(q), "reason": "not in results store (not filed, not fetched, or filer is half-yearly)"} for q in expect if q not in held], "concalls_found": len(calls), "concalls_read": sum(1 for c in calls if c["read"]), "latest_concall": max([c["day"] for c in calls], default=None)}
    d["annual_report"] = arf.get(i)
    d["claims"] = claims_of(i)
    d["completeness"]["annual_report_fy"] = (arf.get(i) or {}).get("fy")
    d["business_group"] = biz.get(i)
    d["note"] = "Verdict v2.1 (tier + tags); business groups are v0 (machine-grouped from annual reports); not investment advice"
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
