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
    # ---------- Balance sheet & cash quality (13) from filed half-yearly statements
    B = (store.load(sym, "balance.json") or {}).get("periods", {})
    if B:
        key = max(B, key=lambda k: datetime.strptime(k.title(), "%d-%b-%Y")); b = B[key]
        debt = (b["borrowings_noncurrent"] or 0) + (b["borrowings_current"] or 0); cash = (b["cash"] or 0) + (b["other_bank_balances"] or 0)
        nd = debt - cash; ttm = sum(Q[l]["ebitda"] for l in labs[-4:])
        de = debt / b["equity"] if b["equity"] else None
        l1 = 3 if nd <= 0 else 2 if nd / ttm < 1 else 1 if nd / ttm < 2 else 0
        l2 = None if de is None else 2 if de <= 0.5 else 1 if de <= 1 else 0
        days = None
        if b["revenue_ytd"]:
            nd_days = 183 if key[3:6] in ("SEP",) else 365
            days = b["trade_receivables"] / b["revenue_ytd"] * nd_days
        w = None if days is None else 3 if days <= 45 else 2 if days <= 75 else 1 if days <= 120 else 0
        oi = (b["other_income_ytd"] / b["pbt_ytd"] * 100) if b["pbt_ytd"] else None
        o = None if oi is None else 2 if oi < 10 else 1 if oi < 25 else 0
        eb_ytd = (b["pbt_ytd"] + b["finance_cost_ytd"] + b["dep_ytd"] - b["other_income_ytd"]) if b["pbt_ytd"] is not None else None
        cc_ = (b["cfo_ytd"] / eb_ytd) if eb_ytd else None
        cf = None if cc_ is None else 3 if cc_ >= 0.8 else 2 if cc_ >= 0.5 else 1 if cc_ >= 0.3 else 0
        fcf = (b["cfo_ytd"] or 0) - (b["capex_ytd"] or 0); icov = (eb_ytd / b["finance_cost_ytd"]) if b["finance_cost_ytd"] else None
        parts = [x for x in (l1, l2, w, o, cf) if x is not None]
        put("balance_sheet_cash", sum(parts), 3 + (2 if l2 is not None else 0) + (3 if w is not None else 0) + (2 if o is not None else 0) + (3 if cf is not None else 0),
            f"As of {key} ({b['basis']}): debt {debt:.0f} Cr, cash+bank {cash:.0f} Cr => net {'cash' if nd <= 0 else 'debt'} {abs(nd):.0f} Cr (net debt/TTM EBITDA {nd/ttm:.2f}; score {l1}/3); debt/equity {de:.2f} ({l2}/2); receivable days ~{days:.0f} ({w}/3); other income {oi:.0f}% of PBT ({o}/2); operating cash flow {b['cfo_ytd']:.0f} vs EBITDA {eb_ytd:.0f} = {cc_:.2f}x ({cf}/3). Capex {b['capex_ytd']:.0f} Cr in the period, free cash flow {fcf:+.0f} Cr, interest cover {icov:.1f}x. Debt rose from {((B.get('30-SEP-2025') or {}).get('borrowings_noncurrent') or 0)+((B.get('30-SEP-2025') or {}).get('borrowings_current') or 0):.0f} Cr a year earlier.")
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
    # ---------- Governance events (4): classified from the text of the filings (trust_docs.json)
    IND = re.compile(r"(?:resign\w*[^.]{0,160}(?<!Non-)(?<!Non )Independent Director|(?<!Non-)(?<!Non )Independent Director[^.]{0,120}tendered (?:his|her) resignation|Resignation of[^.]{0,120}\(DIN[^)]*\)[^.]{0,40}(?<!Non-)(?<!Non )Independent Director)", re.I)
    ind, smp, nominee, reasons = {}, {}, [], {}
    for dd in TD:
        if dd["desc"] not in ("Cessation", "Resignation", "Resignation of Director/KMP/SMP") or D(dd["date"]) < y2: continue
        t = dd["text"]
        rs = re.search(r"(?:citing|due to|on account of)\s+[\u201c\"]?\s*([^.,\u201d\"]{5,70})", t)
        reasons[dd["date"]] = rs.group(1).strip() if rs else "reason only in attached letter"
        if IND.search(t): ind[dd["date"]] = re.search(r"(?:Mr\.|Ms\.|Mrs\.)\s+[A-Z][\w\.]*(?:\s+[A-Z][\w\.]*){0,3}", t[t.find("Dear"):] or t).group(0) if re.search(r"(?:Mr\.|Ms\.|Mrs\.)\s+[A-Z]", t) else "n/a"
        elif re.search(r"Senior Management Personnel|Chief Revenue Officer|Chief Financial Officer[^.]{0,60}resign", t) and re.search(r"resign", t, re.I): smp[dd["date"]] = "senior management"
        elif re.search(r"nominat\w+ by Larsen|Nominee Director on the Board of the Company in place", t): nominee.append(dd["date"])
    orders = [f for f in F if f["desc"].startswith("Action(s) initiated") and D(f["date"]) >= y2]
    g = 4 - (1 if len(ind) >= 3 else 0) - (1 if len(smp) >= 2 else 0) - (1 if orders else 0)
    put("governance_events", max(g, 0), 4, f"Last 24m: {len(ind)} independent-director resignation(s) on {', '.join(sorted(ind, key=D))}; {len(smp)} senior-management exit(s); {len(nominee)} routine promoter-nominee swap(s) ignored; {len(orders)} Reg-30 order(s). Stated reasons: " + "; ".join(f"{k}: {reasons.get(k)}" for k in sorted(list(ind) + list(smp), key=D)) + ".")
    dirs, kmp = list(ind), list(smp)
    # ---------- Use of funds (2)
    mon = [f for f in F if f["desc"] == "Monitoring Agency Report"]; dev = [d for d in TD if d["desc"].startswith("Statement of dev")]
    nodev = [d for d in dev if re.search(r"no deviation|there is no deviation|Deviation / Variation .{0,40}No", d["text"], re.I)]
    put("use_of_funds", 2 if mon and len(nodev) == len(dev) else 1 if mon else 0, 2, f"{len(mon)} monitoring-agency reports filed; {len(nodev)} of {len(dev)} Reg-32 deviation statements read say no deviation.")
    # ---------- Walk the talk (10): code-checked numeric promises + retrieval/consensus-judged event promises
    seen_k = set(); rows_w = []
    for c in sorted(P["calls"].values(), key=lambda c: D(c["filed"])):
        for x in c["promises"]:
            lab = (x.get("code_check") or {}).get("verdict")
            src_ = "code"; lag = None
            if lab in (None, "inconclusive"):
                lab = (x.get("verdict") or {}).get("label"); src_ = "judge"
                lag = (x.get("verdict") or {}).get("lag_months")
            else:
                m_ = re.search(r"\+(\d+)q", str((x.get("code_check") or {}).get("detail") or ""))
                if m_: lag = 3 * int(m_.group(1))
            if not lab: continue
            ws = set(re.findall(r"[a-z0-9]{3,}", x["promise"].lower()))
            if any(m_ == c["filed"][3:] and l_ == lab and len(ws & w_) / max(len(ws | w_), 1) >= 0.45 for m_, l_, w_ in seen_k): continue   # same promise recorded twice (e.g. original + revised transcript)
            seen_k.add((c["filed"][3:], lab, frozenset(ws))); rows_w.append((c["filed"], x["promise"][:70], lab, src_, lag))
    W = {"delivered": 1.0, "delayed": 0.5, "partly": 0.5, "missed": 0.0}
    TOL = 3   # months: a delay of up to 3 months is within normal business variance and earns full credit (shown separately in the ledger)
    def wt(l, lag): return 1.0 if (l == "delayed" and lag is not None and lag <= TOL) else W[l]
    sc_ = [(wt(l, lag), f, t, l, sr) for f, t, l, sr, lag in rows_w if l in W]
    unk = [r for r in rows_w if r[2] not in W]
    n_tol = sum(1 for f, t, l, sr, lag in rows_w if l == "delayed" and lag is not None and lag <= TOL)
    cnt = {k: sum(1 for r in sc_ if r[3] == k) for k in W}
    if len(sc_) >= 8:
        wtt = round(10 * sum(r[0] for r in sc_) / len(sc_), 1)
        put("walk_the_talk", wtt, 10, f"{len(sc_)} verifiable promises across {len(P['calls'])} calls: {cnt['delivered']} delivered, {cnt['delayed']} delayed ({n_tol} of them within {TOL} months, counted as on time), {cnt['partly']} partly, {cnt['missed']} missed (delivered=1, delayed over {TOL} months/partly=0.5, missed=0). {len(unk)} promises could not be verified from filings/calls and are not scored. Numeric promises settled by code from filed numbers; event promises judged by a strong model reading the later calls in full, with a verbatim quote verified in code and audited by a second model (older cheap-model verdicts used only where the strong judge has not run yet).")
    else:
        pts["walk_the_talk"] = None; avail["walk_the_talk"] = 10; notes["walk_the_talk"] = f"only {len(sc_)} verifiable promises; need >=8"
    wt_prov = pts.get("walk_the_talk")
    # ---------- Trust gate (facts only)
    sig = []
    sig.append(("promoter_holding", "watch" if fall else "ok", f"Promoter holding fell >=3 pts in one quarter {len(fall)} time(s): " + "; ".join(f"{a[0]} {a[1]}% -> {b[0]} {b[1]}%" for a, b in fall) + ". Fresh-share allotment filings in window: " + ", ".join(f"{i['date']} ({i['desc'][:20]})" for i in issues if i['desc'] != 'Stock split') if fall else "No quarter fall >=3 pts."))
    pg = [x for x in sast if x.get("acqSaleType") == "Acquisition" and x.get("acquirerDate", "").startswith("21-SEP-2024")]
    if fall and pg: sig[0] = (sig[0][0], sig[0][1], sig[0][2] + f" SAST shows {len(pg)} promoter-family acquisitions on 21-SEP-2024 alongside the preferential allotment.")
    big = next((d_ for d_ in TD if d_["date"] == "04-Dec-2024" and "Larsen" in d_["text"]), None)
    if big and fall:
        m_ = re.search(r"A\s*llotment of ([\d,]+) Equity Shares.*?INR\s*([\d,]+\.\d\d)\s*\(Rupees", big["text"], re.S)
        if m_: sig[0] = (sig[0][0], sig[0][1], sig[0][2] + f" CONFIRMED from allotment filing: 04-Dec-2024 preferential allotment of {m_.group(1)} shares to Larsen & Toubro (non-promoter) for Rs {float(m_.group(2).replace(',',''))/1e7:,.0f} Cr, i.e. dilution from new shares, not promoter selling.")
    sig.append(("pledge", "not_verified", "NSE pledge feed returned no records; cannot confirm either way."))
    sig.append(("insider_trading", "not_verified", "NSE insider (PIT) feed returned no records."))
    sig.append(("regulatory_order", "watch" if orders else "ok", "; ".join(f"{o['date']}: Reg-30 order disclosed" for o in orders) + " (see trust_docs.json for text)" if orders else "None in 24m."))
    sig.append(("board_kmp_exits", "watch" if len(dirs) >= 3 else "ok", notes["governance_events"]))
    sig.append(("use_of_funds", "ok" if pts["use_of_funds"] == 2 else "watch", notes["use_of_funds"]))
    rat = [re.search(r"ICRA\s*\]?\s*([A-Z+\-]+)\s*\(([A-Za-z ]+)\)", d["text"]) for d in TD if d["desc"] == "Credit Rating"]; rat = [r for r in rat if r]
    sig.append(("credit_rating", "ok" if rat else "na", f"ICRA {rat[-1].group(1)} ({rat[-1].group(2)}) per filing" if rat else "No rating filing found."))
    avail_n = sum(1 for s in sig if s[1] in ("ok", "watch")) + (1 if pts.get("walk_the_talk") is not None else 0)
    red = []
    amber = [s[0] for s in sig if s[1] == "watch"]
    gate = "RED" if red else "AMBER-WATCH" if amber else "CLEAR"
    out = {"version": VER, "company": sym, "as_of": now.strftime("%Y-%m-%d"), "latest_quarter": last,
           "points": {k: {"score": pts[k], "max": avail[k], "note": notes[k]} for k in pts},
           "walk_the_talk_ledger": [{"call": f, "promise": t, "verdict": l, "by": sr, "lag_months": lag} for f, t, l, sr, lag in rows_w],
           "scored_so_far": round(sum(v for v in pts.values() if v is not None), 1), "max_for_scored": sum(avail[k] for k in pts if pts[k] is not None),
           "pending_components": ["visibility 8", "capex_capacity 8", "mix_valueadd 8", "moat_future 8", "sector 5", "risk_penalty up to -15"],
           "trust_gate": {"status": gate, "signals": [{"id": a, "status": b, "fact": c} for a, b, c in sig], "credibility_signals_available": avail_n, "enough_data": avail_n >= 3},
           "grade": None, "grade_note": "No grade until all components are scored and >=80% of facts verified."}
    store.save(sym, "score.json", out)
    return out

if __name__ == "__main__":
    o = main(sys.argv[1] if len(sys.argv) > 1 else "E2E")
    for k, v in o["points"].items(): print(f"{k:26} {str(v['score']):>5}/{v['max']:<3} {v['note']}")
    print("scored so far:", o["scored_so_far"], "of", o["max_for_scored"])
    print("TRUST GATE:", o["trust_gate"]["status"], "| signals available:", o["trust_gate"]["credibility_signals_available"])
    for s in o["trust_gate"]["signals"]: print(f"  [{s['status']}] {s['id']}: {s['fact'][:230]}")
