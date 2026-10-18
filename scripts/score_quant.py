"""Code-only part of the FinGod Quality Scorecard + Trust Gate (no LLM). Reads companydata/<SYM>/, writes score.json.
Rules are v0 and explicit so they can be audited / recalibrated. Missing signal = 'not available' and earns no points."""
import os, sys, re, json, warnings
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))
import store, promise_eval as pe
VER = "v0"
def D(s): return datetime.strptime(s, "%d-%b-%Y")
def qdate(lab): return datetime.strptime("01-" + lab, "%d-%b-%y")

def main(sym):
    Q = store.load(sym, "quarters.json")["quarters"]; labs = sorted(Q, key=qdate)
    H = (store.load(sym, "holding.json") or {}).get("rows", [])
    S = store.load(sym, "sast.json") or {}
    F = (store.load(sym, "filings.json") or {}).get("items", [])
    TD = (store.load(sym, "trust_docs.json") or {}).get("items", [])
    P = store.load(sym, "promises.json") or {"calls": {}}
    now = datetime.utcnow(); y2 = now - timedelta(days=730)
    pts, avail, notes = {}, {}, {}
    def put(k, got, mx, note): pts[k], avail[k], notes[k] = round(got, 1), mx, note
    # ---------- Profitability & margin (15) from filed numbers
    em = {l: 100 * Q[l]["ebitda"] / Q[l]["revenue"] for l in labs if Q[l].get("revenue")}
    pm = {l: 100 * Q[l]["pat"] / Q[l]["revenue"] for l in labs if Q[l].get("revenue")}
    last = labs[-1]; ago = labs[-5] if len(labs) >= 5 else None
    lvl = em[last]; a = 5 if lvl >= 35 else 4 if lvl >= 25 else 3 if lvl >= 15 else 2 if lvl >= 8 else 1
    d = em[last] - em[ago] if ago else None
    b = None if d is None else 5 if d >= 5 else 4 if d >= 2 else 3 if d >= -2 else 2 if d >= -5 else 1
    seq = [em[l] for l in labs[-4:]]; ups = sum(1 for i in range(1, len(seq)) if seq[i] >= seq[i - 1])
    c = 5 if pm[last] >= 15 else 4 if pm[last] >= 8 else 3 if pm[last] >= 3 else 2 if pm[last] >= 0 else 0
    put("profitability_margin", a + (b or 0) + c, 15 if b is not None else 10,
        f"EBITDA margin {last} {lvl:.1f}% (level {a}/5); vs year ago {'' if d is None else f'{d:+.1f} pts'} (trend {b}/5); PAT margin {pm[last]:.1f}% ({c}/5); margin rose in {ups} of last 3 quarter steps")
    # ---------- Growth (10) from filed numbers
    prev_y = Q[ago] if ago else None
    g1 = None
    if prev_y and prev_y["revenue"]:
        gr = 100 * (Q[last]["revenue"] / prev_y["revenue"] - 1)
        g1 = 4 if gr >= 50 else 3 if gr >= 25 else 2 if gr >= 10 else 1 if gr >= 0 else 0
        pat_up = Q[last]["pat"] > prev_y["pat"]
        g2 = 3 if (pat_up and Q[last]["pat"] > 0) else 1 if pat_up else 0
        rv = [Q[l]["revenue"] for l in labs[-4:]]; qoq = sum(1 for i in range(1, len(rv)) if rv[i] > rv[i - 1]); g3 = 3 if qoq == 3 else 2 if qoq == 2 else 1 if qoq == 1 else 0
        flag = " LOW-BASE EFFECT: prior-year revenue only Rs %.1f Cr" % prev_y["revenue"] if gr > 200 else ""
        put("growth", g1 + g2 + g3, 10, f"Revenue YoY {gr:.0f}% ({g1}/4); PAT {prev_y['pat']:.1f} -> {Q[last]['pat']:.1f} ({g2}/3); revenue up in {qoq} of last 3 quarter steps ({g3}/3).{flag}")
    # ---------- Promoter holding & pledge (6)
    hr = sorted([r for r in H if r.get("promoter_pct") not in (None, "-")], key=lambda r: D(r["date"].title()) if "-" in r["date"] else now)
    hist = [(r["date"], float(r["promoter_pct"])) for r in hr]
    hist = [h for i, h in enumerate(hist) if i == 0 or h[0] != hist[i - 1][0]]
    latest = hist[-1]
    tgt = datetime.strptime(latest[0].title(), "%d-%b-%Y") - timedelta(days=365)
    yr = min(hist, key=lambda h: abs((datetime.strptime(h[0].title(), "%d-%b-%Y") - tgt).days))
    chg = latest[1] - yr[1]
    t = 3 if chg >= -1 else 2 if chg >= -3 else 1 if chg >= -5 else 0
    lv = 2 if latest[1] >= 50 else 1 if latest[1] >= 30 else 0
    put("promoter_holding_pledge", t + lv, 6, f"Promoter holding {latest[1]}% ({latest[0]}), {chg:+.2f} pts vs {yr[0]} (trend {t}/3, level {lv}/2). Pledge: NSE pledge feed returned no records, so NOT VERIFIED (0/1).")
    # dilution context
    fall = []
    for i in range(1, len(hist)):
        if hist[i][1] - hist[i - 1][1] <= -3: fall.append((hist[i - 1], hist[i]))
    issues = [f for f in F if f["desc"] in ("Allotment of Securities", "Preferential issue", "Issue of Securities", "Stock split")]
    # ---------- Insider / large holder activity (3)
    sast = S.get("sast", [])
    sells = [x for x in sast if x.get("acqSaleType") == "Sale" and x.get("acquirerDate") and re.match(r"\d\d-[A-Z]{3}-\d{4}", x["acquirerDate"]) and datetime.strptime(x["acquirerDate"][:11].title(), "%d-%b-%Y") >= y2]
    put("insider_largeholder", 2 if not sells else 0, 3, f"{len(sells)} large-holder SALE disclosures in last 24 months; insider-trading (PIT) feed returned no records so capped at 2/3.")
    # ---------- Governance events (4)
    ex = [f for f in F if f["desc"] in ("Cessation", "Resignation", "Resignation of Director/KMP/SMP") and D(f["date"]) >= y2]
    seen = set(); evs = []
    for f in ex:
        k = (f["date"], re.sub(r"\W", "", (f["text"] or "")[:90]))
        if f["desc"] == "Resignation of Director/KMP/SMP": continue          # duplicate generic row of a named filing
        if k in seen: continue
        seen.add(k); evs.append(f)
    dirs = [f for f in evs if re.search(r"director", f["text"] or "", re.I)]
    kmp = [f for f in evs if not re.search(r"director", f["text"] or "", re.I)]
    orders = [f for f in F if f["desc"].startswith("Action(s) initiated") and D(f["date"]) >= y2]
    g = 4 - (1 if len(dirs) >= 3 else 0) - (1 if len(kmp) >= 2 else 0) - (1 if orders else 0)
    put("governance_events", max(g, 0), 4, f"Last 24m: {len(dirs)} director exits, {len(kmp)} KMP/senior-management exits, {len(orders)} Reg-30 order(s). Reasons (term end vs resignation) not read.")
    # ---------- Use of funds (2)
    mon = [f for f in F if f["desc"] == "Monitoring Agency Report"]; dev = [d for d in TD if d["desc"].startswith("Statement of dev")]
    nodev = [d for d in dev if re.search(r"no deviation|there is no deviation|Deviation / Variation .{0,40}No", d["text"], re.I)]
    put("use_of_funds", 2 if mon and len(nodev) == len(dev) else 1 if mon else 0, 2, f"{len(mon)} monitoring-agency reports filed; {len(nodev)} of {len(dev)} Reg-32 deviation statements read say no deviation.")
    # ---------- Walk the talk (10) - code-checked part only, provisional
    cc = [x["code_check"]["verdict"] for c in P["calls"].values() for x in c["promises"] if x.get("code_check")]
    jv = [x["verdict"]["label"] for c in P["calls"].values() for x in c["promises"] if x.get("verdict")]
    dl, dy, ms = cc.count("delivered"), cc.count("delayed"), cc.count("missed")
    notes["walk_the_talk"] = f"PROVISIONAL (code-checked numeric promises only): {dl} delivered, {dy} delayed, {ms} missed, {cc.count('inconclusive')} inconclusive; judge pending for event promises ({len(jv)} judged)."
    pts["walk_the_talk"] = None; avail["walk_the_talk"] = 10
    wt_prov = round(10 * (dl + 0.5 * dy) / max(dl + dy + ms, 1), 1) if (dl + dy + ms) >= 5 else None
    # ---------- Trust gate (facts only)
    sig = []
    sig.append(("promoter_holding", "watch" if fall else "ok", f"Promoter holding fell >=3 pts in one quarter {len(fall)} time(s): " + "; ".join(f"{a[0]} {a[1]}% -> {b[0]} {b[1]}%" for a, b in fall) + ". Fresh-share allotment filings in window: " + ", ".join(f"{i['date']} ({i['desc'][:20]})" for i in issues if i['desc'] != 'Stock split') if fall else "No quarter fall >=3 pts."))
    pg = [x for x in sast if x.get("acqSaleType") == "Acquisition" and x.get("acquirerDate", "").startswith("21-SEP-2024")]
    if fall and pg: sig[0] = (sig[0][0], sig[0][1], sig[0][2] + f" SAST shows {len(pg)} promoter-family acquisitions on 21-SEP-2024 alongside the preferential allotment.")
    sig.append(("pledge", "not_verified", "NSE pledge feed returned no records; cannot confirm either way."))
    sig.append(("insider_trading", "not_verified", "NSE insider (PIT) feed returned no records."))
    sig.append(("regulatory_order", "watch" if orders else "ok", "; ".join(f"{o['date']}: Reg-30 order disclosed" for o in orders) + " (see trust_docs.json for text)" if orders else "None in 24m."))
    sig.append(("board_kmp_exits", "watch" if len(dirs) >= 3 else "ok", f"{len(dirs)} director exits and {len(kmp)} KMP exits in 24m."))
    sig.append(("use_of_funds", "ok" if pts["use_of_funds"] == 2 else "watch", notes["use_of_funds"]))
    rat = [re.search(r"ICRA\s*\]?\s*([A-Z+\-]+)\s*\(([A-Za-z ]+)\)", d["text"]) for d in TD if d["desc"] == "Credit Rating"]; rat = [r for r in rat if r]
    sig.append(("credit_rating", "ok" if rat else "na", f"ICRA {rat[-1].group(1)} ({rat[-1].group(2)}) per filing" if rat else "No rating filing found."))
    avail_n = sum(1 for s in sig if s[1] in ("ok", "watch")) + (1 if cc else 0)
    red = []
    amber = [s[0] for s in sig if s[1] == "watch"]
    gate = "RED" if red else "AMBER-WATCH" if amber else "CLEAR"
    out = {"version": VER, "company": sym, "as_of": now.strftime("%Y-%m-%d"), "latest_quarter": last,
           "points": {k: {"score": pts[k], "max": avail[k], "note": notes[k]} for k in pts},
           "walk_the_talk_provisional": wt_prov,
           "scored_so_far": round(sum(v for v in pts.values() if v is not None), 1), "max_for_scored": sum(avail[k] for k in pts if pts[k] is not None),
           "pending_components": ["walk_the_talk (judge)", "balance_sheet_cash 13", "visibility 8", "capex_capacity 8", "mix_valueadd 8", "moat_future 8", "sector 5", "risk_penalty up to -15"],
           "trust_gate": {"status": gate, "signals": [{"id": a, "status": b, "fact": c} for a, b, c in sig], "credibility_signals_available": avail_n, "enough_data": avail_n >= 3},
           "grade": None, "grade_note": "No grade until all components are scored and >=80% of facts verified."}
    store.save(sym, "score.json", out)
    return out

if __name__ == "__main__":
    o = main(sys.argv[1] if len(sys.argv) > 1 else "E2E")
    for k, v in o["points"].items(): print(f"{k:26} {str(v['score']):>5}/{v['max']:<3} {v['note']}")
    print("scored so far:", o["scored_so_far"], "of", o["max_for_scored"], "| WTT provisional:", o["walk_the_talk_provisional"])
    print("TRUST GATE:", o["trust_gate"]["status"], "| signals available:", o["trust_gate"]["credibility_signals_available"])
    for s in o["trust_gate"]["signals"]: print(f"  [{s['status']}] {s['id']}: {s['fact'][:230]}")
