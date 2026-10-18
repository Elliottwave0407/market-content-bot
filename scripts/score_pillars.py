"""Code-only scoring of the qualitative pillars from audit-confirmed facts (pillars.json) + filed numbers (balance.json, promises).
v0 rules, explicit so they can be audited / recalibrated. A fact that is missing, unverified or audit-rejected earns 0 and is reported
as 'not disclosed / not verified'. Writes companydata/<SYM>/pillars_score.json."""
import os, sys, re, json
sys.path.insert(0, os.path.dirname(__file__))
import store
VER = "v0"
def main(sym):
    P = store.load(sym, "pillars.json") or {"facts": []}
    B = (store.load(sym, "balance.json") or {}).get("periods", {})
    S = store.load(sym, "score.json") or {}
    F = {}
    for f in P["facts"]:
        top = f["path"].strip("/").split("[")[0].split("/")[0]
        F.setdefault(top, []).append(f["fact"])
    def one(k): return (F.get(k) or [None])[0]
    def num(x, k):
        try: return float(x.get(k))
        except Exception: return None
    pts, avail, notes = {}, {}, {}
    def put(k, got, mx, note): pts[k], avail[k], notes[k] = round(got, 1), mx, note
    # ---- Visibility (8)
    v = 0; n = []
    r = one("recurring_share_pct"); rv = num(r, "value") if r else None
    if rv is not None: s = 3 if rv >= 70 else 2 if rv >= 50 else 1; v += s; n.append(f"recurring/contracted revenue share {rv:g}% ({s}/3)")
    else: n.append("recurring share not disclosed (0/3)")
    c = one("customer_concentration"); cv = num(c, "share_pct") if c else None
    if cv is not None: s = 2 if cv < 40 else 1 if cv <= 70 else 0; v += s; n.append(f"top-{c.get('top_n')} customers {cv:g}% of revenue ({s}/2)")
    else: n.append("customer concentration not disclosed (0/2)")
    if one("contracted_demand"): v += 1.5; n.append("contracted / committed demand stated (1.5/1.5)")
    else: n.append("no contracted-demand statement verified (0/1.5)")
    g = [x for x in F.get("quantified_guidance", []) if re.search(r"\d", json.dumps(x))]
    if g: s = 1.5 if len(g) >= 2 else 1; v += s; n.append(f"{len(g)} quantified guidance item(s) ({s}/1.5)")
    else: n.append("no quantified guidance verified (0/1.5)")
    put("visibility", min(v, 8), 8, "; ".join(n))
    # ---- Capex & capacity (8)
    v = 0; n = []
    cp = one("capex_plan")
    if cp and num(cp, "amount_cr"): v += 2; n.append(f"capex plan Rs {num(cp,'amount_cr'):g} Cr {cp.get('period') or ''} stated (2/2)")
    else: n.append("no quantified capex plan verified (0/2)")
    last = sorted(B, key=lambda k: __import__("datetime").datetime.strptime(k, "%d-%b-%Y"))[-1] if B else None
    if last:
        b = B[last]; capex = b.get("capex_ytd") or 0; cfo = b.get("cfo_ytd") or 0
        debt = (b.get("borrowings_current") or 0) + (b.get("borrowings_noncurrent") or 0); cash = (b.get("cash") or 0) + (b.get("other_bank_balances") or 0)
        cov = cfo / capex if capex else None
        s = 2 if (cov is not None and cov >= 0.8) or cash >= debt else 1 if cov is not None and cov >= 0.4 else 0
        v += s; n.append(f"funding: operating cash flow covers {cov:.0%} of period capex (Rs {cfo:g} vs {capex:g} Cr), net cash {cash-debt:+.0f} Cr ({s}/2)" if cov is not None else f"funding: capex not available ({s}/2)")
    cap_rows = [r for r in S.get("walk_the_talk_ledger", []) if re.search(r"capex|capacity|GPU|zone|cluster|deploy|data ?cent", r["promise"], re.I) and r["verdict"] in ("delivered", "delayed", "partly", "missed")]
    if len(cap_rows) >= 3:
        d = sum(1 for r in cap_rows if r["verdict"] == "delivered") / len(cap_rows); s = 2 if d >= 0.7 else 1 if d >= 0.5 else 0
        v += s; n.append(f"capacity promises delivered on time: {d:.0%} of {len(cap_rows)} verifiable ({s}/2)")
    else: n.append(f"only {len(cap_rows)} verifiable capacity promises (0/2)")
    cap = one("capacity"); ret = one("returns_disclosed")
    if (cap and num(cap, "utilization_pct") is not None) or ret: v += 2; n.append("utilisation / returns on capacity disclosed (2/2)")
    else: n.append("no utilisation or returns disclosure verified (0/2)")
    put("capex_capacity", min(v, 8), 8, "; ".join(n))
    # ---- Product mix & value-add (8)
    v = 0; n = []
    seg = [x for x in F.get("segments", []) if num(x, "share_pct") is not None]
    if len(seg) >= 2: v += 2; n.append(f"{len(seg)} segment shares disclosed: " + ", ".join(f"{x.get('name')} {num(x,'share_pct'):g}%" for x in seg[:4]) + " (2/2)")
    else: n.append("segment mix not verified (0/2)")
    va = one("value_added"); vs = num(va, "share_pct") if va else None
    if va: s = 2 if vs is not None and vs >= 20 else 1; v += s + (1 if False else 0); n.append(f"value-added / platform offering: {va.get('detail','')[:70]}" + (f" ({vs:g}% of revenue)" if vs is not None else "") + f" ({s}/2)")
    else: n.append("no value-added share verified (0/2)")
    sm = one("segment_margin")
    if sm: v += 2; n.append("margin by segment/product discussed (2/2)")
    else: n.append("no segment-margin evidence verified (0/2)")
    if len(seg) >= 2 and va: v += 2; n.append("mix + value-add both evidenced (2/2)")
    put("product_mix", min(v, 8), 8, "; ".join(n))
    # ---- Moat & roadmap (8)
    mo = F.get("moat", []); lt = [x for x in F.get("long_term_targets", []) if x.get("by")]
    v = min(len(mo), 3) * 2 + (2 if lt else 0)
    put("moat_roadmap", min(v, 8), 8, f"{len(mo)} verified barrier statement(s) (2 each, max 3): " + "; ".join(x.get("barrier", "")[:50] for x in mo[:3]) + f"; {len(lt)} dated long-term target(s) verified ({2 if lt else 0}/2). Barriers are management's own claims, shown as such.")
    # ---- Sector (5)
    sc = F.get("sector", []); v = min(len(sc), 3) + (2 if len(sc) >= 3 else 0)
    put("sector_positioning", min(v, 5), 5, f"{len(sc)} verified sector/positioning statement(s) (1 each up to 3; +2 if >=3).")
    # ---- Risk penalty (0 to -15): verified risks + code-measured risks
    pen = 0; n = []
    rk = F.get("risks", []); seen = set()
    W = {"concentration": 3, "regulatory": 3, "execution": 2, "funding": 3, "supply": 2, "competition": 2}
    for x in rk:
        t = (x.get("type") or "").lower().split("|")[0]
        if t in W and t not in seen: seen.add(t); pen += W[t]; n.append(f"{t} risk stated (-{W[t]})")
    if last:
        b = B[last]
        if (b.get("cfo_ytd") or 0) - (b.get("capex_ytd") or 0) < 0: pen += 2; n.append("free cash flow negative in latest period (-2)")
        d_now = (b.get("borrowings_current") or 0) + (b.get("borrowings_noncurrent") or 0)
        prev = [k for k in B if k[3:] == last[3:] and k != last]
    pen = min(pen, 15)
    put("risk_penalty", -pen, -15, "; ".join(n) or "no risk items verified")
    out = {"version": VER, "points": {k: {"score": pts[k], "max": avail[k], "note": notes[k]} for k in pts}, "pillars_facts_confirmed": len(P["facts"]), "from": {"extracted_on": P.get("extracted_on"), "extract_model": P.get("extract_model"), "audit_model": P.get("audit_model")}}
    store.save(sym, "pillars_score.json", out)
    return out
if __name__ == "__main__":
    o = main(os.environ.get("SYMBOL", "E2E").strip().upper())
    for k, v in o["points"].items(): print(f"{k:20} {v['score']:5}/{v['max']}  {v['note'][:230]}")
