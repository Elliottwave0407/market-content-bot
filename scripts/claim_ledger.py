"""Claim ledger v1 (24 Nov 2026): one append-only list of management claims per company (ISIN), built from concall facts, presentation facts and
annual report facts, each backed by the share price on the claim date. Code only, no model, no posting.
Output: store/claim_ledger/<ISIN>.json, _index.json, _stats.json.   usage: python3 scripts/claim_ledger.py [OUT_DIR]"""
import os, sys, json, glob, gzip, bisect, hashlib, re, collections
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store") + "/"
OUT = (sys.argv[1] if len(sys.argv) > 1 else R + "claim_ledger") + "/"; os.makedirs(OUT, exist_ok=True)
CATS = {"guidance", "capex", "capacity", "order_book", "margin"}
mc = json.load(open(R + "mcap/mcap.json"))
scrip2isin = {m.get("s"): i for i, m in mc.items() if m.get("s")}
sym2isin = {}
for l in open(R + "results_if/numbers.jsonl"):
    r = json.loads(l)
    if r.get("isin") and r.get("sym"): sym2isin[r["sym"]] = r["isin"]
def isin_of(code):
    if not code: return None
    return sym2isin.get(code[4:]) if code.startswith("NSE:") else scrip2isin.get(code)
# prices: close by ISIN and date (NSE file preferred, BSE fills gaps)
px = collections.defaultdict(dict); days = set()
for f in sorted(glob.glob(R + "prices/d/*.csv.gz")):
    d = os.path.basename(f)[:10]; days.add(d)
    for l in gzip.open(f, "rt"):
        a = l.split(",")
        if len(a) > 8 and a[4] in ("EQ", "A", "B", "T", "X", "XT", "Z", "SM", "ST", "BE", "BZ", "M", "MT", "P", "R", "S", "W", "MS", "MP"):
            try:
                if d not in px[a[2]] or a[1] == "N": px[a[2]][d] = float(a[8])
            except Exception: pass
days = sorted(days)
SNAP = [1/2, 1/3, 1/4, 1/5, 1/10, 2/3, 3/4, 1/20, 1/8, 1/6]
adj_done = {}
def adjusted(isin):
    """split/bonus adjustment: a one-day close drop of 35%+ that sits near a clean ratio is treated as a corporate action (demergers are not handled)."""
    if isin in adj_done: return adj_done[isin]
    s = px.get(isin) or {}; ds = sorted(s); out = dict(s); f = 1.0; flags = 0
    for k in range(len(ds) - 1, 0, -1):
        r = s[ds[k]] / s[ds[k - 1]] if s[ds[k - 1]] else 1
        if r < 0.65 and any(abs(r - x) / x < 0.06 for x in SNAP): f *= r; flags += 1
        out[ds[k - 1]] = s[ds[k - 1]] * f
    adj_done[isin] = (out, flags); return adj_done[isin]
def price_ctx(isin, day):
    if not px.get(isin) or not day: return None
    s, nflag = adjusted(isin)
    k = bisect.bisect_left(days, day)
    if k >= len(days): return None
    def at(j):
        j = min(j, len(days) - 1)
        for jj in range(j, max(j - 4, -1), -1):
            if days[jj] in s: return s[days[jj]]
        return None
    p0, p1, p5, last = at(k), at(k + 1), at(k + 5), s[max(s)] if s else None
    if not p0: return None
    out = {"close": round(p0, 1)}
    if nflag: out["split_adjusted"] = True
    if p0 and p1: out["d1_pct"] = round((p1 / p0 - 1) * 100)
    if p0 and p5 and k + 5 < len(days): out["d5_pct"] = round((p5 / p0 - 1) * 100)
    if p0 and last and k < len(days) - 5: out["to_latest_pct"] = round((last / p0 - 1) * 100)
    return out
claims = collections.defaultdict(dict)
def add(isin, source, day, url, it):
    st = (it.get("statement") or "").strip()
    if not isin or not st or it.get("cat") not in CATS: return
    key = hashlib.md5(("%s|%s|%s|%s" % (isin, it["cat"], re.sub(r"\W+", "", st.lower())[:90], it.get("period") or "")).encode()).hexdigest()[:12]
    c = claims[isin].get(key)
    rec = {"source": source, "day": day, "url": url}
    if c is None:
        claims[isin][key] = {"id": key, "cat": it["cat"], "statement": st[:300], "period": it.get("period"), "value": it.get("value"), "direction": it.get("direction"), "first_day": day, "sources": [rec]}
    elif not any(s["source"] == source and s["day"] == day for s in c["sources"]):
        c["sources"].append(rec); c["first_day"] = min(c["first_day"], day)
for f in sorted(glob.glob(R + "concall_facts*/*.jsonl")):
    if "dry" in f: continue
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        isin = r.get("isin") or isin_of(r.get("code"))
        for it in r.get("items") or []: add(isin, "concall", r.get("day"), r.get("src"), it)
for f in sorted(glob.glob(R + "ppt_facts/*.jsonl")):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        for it in r.get("items") or []:
            if it.get("cat") in ("kpi", "outlook"): it = dict(it, cat="guidance") if it.get("cat") == "outlook" else it
            add(r.get("isin"), "presentation", r.get("day"), r.get("url"), it)
for f in glob.glob(R + "annual_report_facts/*.json"):
    try: d = json.load(open(f))
    except Exception: continue
    fa = d.get("facts") or {}
    day = "%d-03-31" % d.get("fy", 0)
    for g in fa.get("guidance_or_targets") or []:
        add(d["isin"], "annual_report", day, d.get("src"), {"cat": "guidance", "statement": g.get("statement") or "", "period": g.get("by_when"), "value": g.get("value")})
    for g in fa.get("capacity_or_capex") or []:
        add(d["isin"], "annual_report", day, d.get("src"), {"cat": "capex", "statement": ("%s %s" % (g.get("item") or "", ("Rs %s crore" % g["amount_cr"]) if g.get("amount_cr") else "")).strip(), "period": g.get("timeline"), "value": g.get("amount_cr")})
idx = []; stats = collections.Counter()
for isin, cs in claims.items():
    L = sorted(cs.values(), key=lambda c: c["first_day"] or "")
    for c in L:
        c["price_at_claim"] = price_ctx(isin, c["first_day"]); stats["claims"] += 1; stats[c["cat"]] += 1; stats["priced"] += c["price_at_claim"] is not None
        for s in c["sources"]: stats["src_" + s["source"]] += 1
    json.dump({"isin": isin, "name": (mc.get(isin) or {}).get("n"), "claims": L}, open(OUT + isin + ".json", "w"), separators=(",", ":"))
    idx.append({"isin": isin, "n": len(L)})
json.dump(idx, open(OUT + "_index.json", "w")); stats["companies"] = len(idx); json.dump(dict(stats), open(OUT + "_stats.json", "w"), indent=1)
print(dict(stats))
