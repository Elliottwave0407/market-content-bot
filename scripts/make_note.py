"""FinGod research note generator. Numbers are computed from companydata/<SYM>/*.json (same sources as make_card.py);
reviewed wording (quotes, ownership/governance, moat, not-disclosed) comes from card_copy.json -> "note".
Usage: python scripts/make_note.py E2E   -> cards/E2E/note.md (and printed)"""
import os, sys, json
from datetime import datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM = (sys.argv[1] if len(sys.argv) > 1 else "E2E").upper()
D = os.path.join(ROOT, "companydata", SYM)
J = lambda n, d=None: json.load(open(os.path.join(D, n))) if os.path.exists(os.path.join(D, n)) else d
Q = J("quarters.json")["quarters"]; SC = J("score.json"); PS = J("pillars_score.json", {"points": {}}); BAL = J("balance.json")["periods"]
COPY = J("card_copy.json", {}); N = COPY.get("note", {}); PROF = J("profile.json", {})
ME = lambda l: datetime.strptime("01-" + l, "%d-%b-%y")
labs = sorted(Q, key=ME); cur, prv, ya = labs[-1], labs[-2], labs[-5]
r0 = lambda x: f"{round(x):,}"
def fyq(l):
    d = ME(l); fy = d.year + (1 if d.month >= 4 else 0); return f"Q{((d.month - 4) % 12) // 3 + 1} FY{str(fy)[2:]}"
rev = lambda l: Q[l]["revenue"]; eb = lambda l: Q[l]["ebitda"]; em = lambda l: 100 * eb(l) / rev(l)
bk = sorted(BAL, key=lambda k: datetime.strptime(k, "%d-%b-%Y")); b = BAL[bk[-1]]; b0 = BAL[bk[0] if False else [k for k in bk if k.startswith("31-MAR-2025")][0]]
bm = [k for k in bk if k.startswith("31-MAR-")]; bprev = BAL[bm[-1]]          # latest full-year balance sheet
debt = lambda x: (x.get("borrowings_current") or 0) + (x.get("borrowings_noncurrent") or 0)
cash = lambda x: (x.get("cash") or 0) + (x.get("other_bank_balances") or 0)
pts = {k: (v["score"], v["max"]) for k, v in SC["points"].items() if v["score"] is not None}; pts.update({k: (v["score"], v["max"]) for k, v in PS["points"].items()})
pen = pts.pop("risk_penalty", (0, 0))[0]; tot = sum(s for s, m in pts.values()) + pen
cap = {"RED": "C", "AMBER-WATCH": "B", "AMBER": "B"}.get(SC["trust_gate"]["status"].upper())
grade = "A" if tot >= 75 else "B" if tot >= 60 else "C" if tot >= 45 else "D"
if cap and grade < cap: grade = cap
TOL = 3; led = [r for r in SC["walk_the_talk_ledger"] if r["verdict"] in ("delivered", "delayed", "partly", "missed")]
unk = [r for r in SC["walk_the_talk_ledger"] if r["verdict"] not in ("delivered", "delayed", "partly", "missed")]
def ok(r): return r["verdict"] == "delivered" or (r["verdict"] == "delayed" and r.get("lag_months") is not None and r["lag_months"] <= TOL)
n_ok = sum(1 for r in led if ok(r)); n_late = sum(1 for r in led if r["verdict"] in ("delayed", "partly") and not ok(r)); n_miss = sum(1 for r in led if r["verdict"] == "missed")
# --- numbers
qg = 100 * (rev(cur) / rev(prv) - 1); d_rev = rev(cur) - rev(prv); d_eb = eb(cur) - eb(prv); inc = 100 * d_eb / d_rev
nq = 2 if datetime.strptime(bk[-1], "%d-%b-%Y").month in (9, 3) else 1
h_eb = sum(eb(l) for l in labs[-nq:]); dep = b["dep_ytd"]; oi = b["other_income_ytd"]; fc = b["finance_cost_ytd"]; pbt = b["pbt_ytd"]; h_rev = b["revenue_ytd"]
cfo = b["cfo_ytd"]; cpx = b["capex_ytd"]; dbt, csh = debt(b), cash(b); d0, c0 = debt(bprev), cash(bprev)
b25 = BAL[[k for k in bk if k.startswith("31-MAR-2025")][0]]; fy_prev_cpx = bprev["capex_ytd"]; fy_prev_cfo = bprev["cfo_ytd"]
rec_days = b["trade_receivables"] / h_rev * (30 * (6 if nq == 2 else 3) + (3 if nq == 2 else 0))
L = []; A = L.append
A(f"**{PROF.get('name', SYM).replace(' Limited','').replace(' Ltd','')} (NSE: {SYM}) · {fyq(cur)} · FinGod Quality Grade {grade} ({tot:.0f}/100)**\n")
A("**1. The thesis**"); A(f"{N.get('thesis_lead','')} revenue ₹{r0(rev(cur))} Cr (₹{r0(rev(ya))} Cr a year ago), EBITDA margin {round(em(cur))}% ({round(em(ya))}%), net profit ₹{r0(Q[cur]['pat'])} Cr ({'loss of ' if Q[ya]['pat']<0 else ''}₹{r0(abs(Q[ya]['pat']))} Cr). {N.get('thesis_tail','')}\n")
A("**2. Results and margin bridge**")
A(f"• Revenue grew {qg:.0f}% on the quarter (₹{r0(rev(prv))} Cr in {fyq(prv)}). EBITDA rose from ₹{r0(eb(prv))} Cr to ₹{r0(eb(cur))} Cr, so the extra ₹{r0(d_rev)} Cr of revenue came with ₹{r0(d_eb)} Cr of EBITDA: an incremental margin of about {round(inc/5)*5}%, {N.get('incr_note','')}")
A(f"• Quality of earnings, H1 FY27: depreciation ₹{r0(dep)} Cr takes {100*dep/h_eb:.0f}% of EBITDA of ₹{r0(h_eb)} Cr, so EBIT margin is about {100*(h_eb-dep)/h_rev:.0f}%, not {100*h_eb/h_rev:.0f}%. Other income ₹{r0(oi)} Cr is {100*oi/pbt:.0f}% of pre-tax profit ₹{r0(pbt)} Cr. Finance cost ₹{r0(fc)} Cr.")
if Q[ya]["basis"] != Q[cur]["basis"]: A(f"• Basis: {ME(ya).strftime('%b-%y')} comparatives are {Q[ya]['basis']} and {ME(cur).strftime('%b-%y')} is {Q[cur]['basis']}, so year-on-year growth is best read alongside the quarter-on-quarter trend.")
A(f"\n**3. Cash and balance sheet**")
A(f"• Operating cash flow ₹{r0(cfo)} Cr ({cfo/h_eb:.1f}x EBITDA) against cash capex ₹{r0(cpx)} Cr: free cash flow {'−' if cfo<cpx else ''}₹{r0(abs(cfo-cpx))} Cr.")
A(f"• Debt ₹{r0(dbt)} Cr, cash and bank ₹{r0(csh)} Cr, net cash ₹{r0(csh-dbt)} Cr (₹{r0(cash(b25)-debt(b25))} Cr in Mar-25). Since then, cash capex of ₹{r0(fy_prev_cpx+cpx)} Cr (FY26 plus H1 FY27) against operating cash flow of ₹{r0(fy_prev_cfo+cfo)} Cr is where the {N.get('money_source','new equity')} money went. Debt has gone from ₹{r0(debt(b25))} Cr to ₹{r0(dbt)} Cr.")
A(f"• Receivables ₹{r0(b['trade_receivables'])} Cr, about {rec_days:.0f} days of H1 revenue.\n")
A("**4. Walk the talk**")
A(f"{len(led)} promises could be checked against what followed, and {len(unk)} could not. Of the {len(led)}, {n_ok} were met (delays up to {TOL} months count as on time), {n_late} was late and {n_miss} missed." if n_late == 1 else f"{len(led)} promises could be checked against what followed, and {len(unk)} could not. Of the {len(led)}, {n_ok} were met (delays up to {TOL} months count as on time), {n_late} were late and {n_miss} missed.")
for k in ("met", "late", "missed", "unchecked"): 
    if N.get("walk", {}).get(k): A(N["walk"][k])
A(N.get("walk", {}).get("pattern", "") + "\n")
A("**5. Beyond the numbers**")
for x in N.get("beyond", []): A("• " + x)
A("\n**6. What is not disclosed**")
for x in N.get("undisclosed", []): A("• " + x)
A("\n*Not a price target or buy/sell view. For educational purposes only.*")
nm_ = PROF.get("name", SYM).replace(" Limited", "").replace(" Ltd", "")
tweet = (f"{nm_} {fyq(cur)}: revenue ₹{r0(rev(cur))} Cr (₹{r0(rev(ya))} Cr a year ago), EBITDA margin {round(em(cur))}% ({round(em(ya))}%), net profit ₹{r0(Q[cur]['pat'])} Cr. "
         f"FinGod Quality Grade {grade} ({tot:.0f}/100). Walk the talk: {n_ok}/{len(led)} promises on time.\n" + N.get("tags", f"#{SYM}"))
os.makedirs(os.path.join(ROOT, "cards", SYM), exist_ok=True); open(os.path.join(ROOT, "cards", SYM, "tweet.txt"), "w").write(tweet)
out = "\n".join(L); os.makedirs(os.path.join(ROOT, "cards", SYM), exist_ok=True)
open(os.path.join(ROOT, "cards", SYM, "note.md"), "w").write(out + "\n"); print(out)
