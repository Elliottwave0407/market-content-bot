"""Data-driven FinGod company card (tall, 1080 wide) -> HTML -> PNG at 2x via Playwright.
Numbers come from companydata/<SYM>/*.json (quarters, balance, holding, score, pillars, pillars_score, promises ledger).
Narrative lines come from companydata/<SYM>/card_copy.json (reviewed wording). Grade stays '?' until the gate passes
(all pillars scored AND >=80% of extracted facts audit-confirmed).
Usage: python scripts/make_card.py E2E [--final]   -> cards/E2E/card.html, card.png (draft watermark unless --final)"""
import os, re, sys, json
from datetime import datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM = (sys.argv[1] if len(sys.argv) > 1 else "E2E").upper(); FINAL = "--final" in sys.argv
D = os.path.join(ROOT, "companydata", SYM)
def J(n, d=None):
    try: return json.load(open(os.path.join(D, n)))
    except Exception: return d
Q = J("quarters.json")["quarters"]; SC = J("score.json"); PS = J("pillars_score.json", {"points": {}}); PL = J("pillars.json", {"facts": [], "rejected": [], "n_extracted": 0})
COPY = J("card_copy.json", {}); PROF = J("profile.json", {}); BAL = J("balance.json")["periods"]; HOLD = J("holding.json")["rows"]
ME = lambda l: datetime.strptime("01-" + l, "%d-%b-%y")
labs = sorted(Q, key=ME); L8 = labs[-8:]; cur = labs[-1]; ya = labs[-5]
rev = {l: Q[l]["revenue"] for l in labs}; em = {l: 100 * Q[l]["ebitda"] / Q[l]["revenue"] for l in labs}
def r0(x): return f"{round(x):,}"
def money(x): return ("−" if x < 0 else "") + "₹" + r0(abs(x)) + " Cr"
def fylabel(l):
    d = ME(l); fy = d.year + (1 if d.month >= 4 else 0); q = ((d.month - 4) % 12) // 3 + 1
    return f"Q{q} FY{str(fy)[2:]} ({l})"
# ---------- walk the talk from the ledger (3-month tolerance, same rule as score_quant)
TOL = 3
led = [r for r in SC["walk_the_talk_ledger"] if r["verdict"] in ("delivered", "delayed", "partly", "missed")]
unk = [r for r in SC["walk_the_talk_ledger"] if r["verdict"] not in ("delivered", "delayed", "partly", "missed")]
def cls(r):
    if r["verdict"] == "delivered": return "g"
    if r["verdict"] == "delayed" and r.get("lag_months") is not None and r["lag_months"] <= TOL: return "g"
    if r["verdict"] in ("delayed", "partly"): return "a"
    return "r"
nd = sum(1 for r in led if cls(r) == "g"); nl = sum(1 for r in led if cls(r) == "a"); nm = sum(1 for r in led if cls(r) == "r"); n = len(led)
CATS = [("Revenue &amp; margin targets", r"\b(revenue|mrr|ebitda|margin|pat|grow\w*|arr)\b"), ("Capacity &amp; capex", r"capex|gpu|capacity|deploy|hardware|blackwell|cluster|b200"), ("Product / site launches", r"\b(zone|location|facility|site|launch\w*)\b"), ("Funding", r"\b(fund\w*|raise|equity|debt|financ\w*)\b")]
BUCKET_ORDER = [3, 2, 1, 0]   # funding first, then site launches, then capacity, then revenue
def bucket(t):
    for i in BUCKET_ORDER:
        if re.search(CATS[i][1], t, re.I): return i
    return None
cat_n = [[0, 0, 0] for _ in CATS]
for r in led:
    b = bucket(r["promise"])
    if b is not None: cat_n[b][{"g": 0, "a": 1, "r": 2}[cls(r)]] += 1
# ---------- pillars + gate
pts = {k: (v["score"], v["max"]) for k, v in SC["points"].items() if v["score"] is not None}
pp = {k: (v["score"], v["max"]) for k, v in PS["points"].items()}
allp = {**pts, **pp}; pen = allp.pop("risk_penalty", (0, -15))[0]
tot = sum(s for s, m in allp.values()) + pen; mxp = sum(m for s, m in allp.values())
nfacts = len(PL["facts"]); next_ = max(PL.get("n_extracted") or 0, 1); vpct = 100 * nfacts / next_
n_pillars = len(allp) + (1 if "risk_penalty" in PS["points"] else 0)
gate = SC["trust_gate"]["status"]; cap = {"RED": "C", "AMBER-WATCH": "B", "AMBER": "B"}.get(gate.upper())
grade = None
if vpct >= 80 and n_pillars >= 14:
    g = "A" if tot >= 75 else "B" if tot >= 60 else "C" if tot >= 45 else "D"
    if cap and g < cap: g = cap
    grade = g
MARK = "file://" + os.path.join(ROOT, "assets", "fingod_mark.png"); FD = "file://" + os.path.join(ROOT, "assets", "fonts") + "/"
fonts = "".join(f"@font-face{{font-family:'Plex';font-weight:{w};src:url('{FD}ibm-plex-sans-latin-{w}-normal.woff2')}}" for w in (400, 500, 600, 700))
fonts += "".join(f"@font-face{{font-family:'PlexC';font-weight:{w};src:url('{FD}ibm-plex-sans-condensed-latin-{w}-normal.woff2')}}" for w in (500, 600, 700))
CSS = fonts + """
:root{--navy:#0b1f3a;--ink:#14213a;--mut:#5b6b82;--line:#d3dae5;--soft:#f1f4f9;--g:#0e8f63;--a:#b86e00;--r:#c0392b;--blue:#3b5b92}
*{box-sizing:border-box;margin:0;padding:0}
html{width:1080px;overflow:hidden}
body{width:1080px;background:#fff;color:var(--ink);font-family:'Plex','IBM Plex Sans',Arial,sans-serif;font-weight:500;display:flex;flex-direction:column;gap:8px;padding:12px 20px 8px;position:relative;overflow:hidden;font-variant-numeric:tabular-nums}
.wm{position:absolute;left:-60px;top:600px;width:1200px;text-align:center;transform:rotate(-22deg);font-size:84px;font-weight:700;color:rgba(192,57,43,.09);letter-spacing:5px;z-index:9}
.hd{display:flex;align-items:center;gap:14px;padding-bottom:7px;border-bottom:3px solid var(--navy)}
.nm{font-size:36px;font-weight:700;letter-spacing:-.4px;line-height:1.05}.tk{font-family:'PlexC';font-size:20px;color:var(--mut);font-weight:600;margin-top:5px;letter-spacing:.2px}
.grade{margin-left:auto;border:1.5px solid var(--navy);border-radius:6px;padding:3px 12px;text-align:center;min-width:190px}
.grade .t{font-family:'PlexC';font-size:17px;letter-spacing:1px;color:var(--mut);font-weight:700;text-transform:uppercase}.grade .q{font-size:30px;font-weight:700;line-height:1;color:#9aa6b8}.grade .q.ok{color:var(--navy);font-size:34px}.grade .s{font-family:'PlexC';font-size:18px;color:var(--mut);font-weight:600}
.mark{height:62px}
.band{background:var(--navy);color:#fff;border-radius:6px;padding:9px 16px;font-size:24px;line-height:1.26;font-weight:600;letter-spacing:-.1px}
.band span{color:#8fd9b6}.band b{color:#ffd48a;font-weight:600}
.kp{display:flex;gap:8px}.kp>div{flex:1;border:1px solid var(--line);border-radius:6px;padding:7px 10px;background:var(--soft)}
.kp .l{font-family:'PlexC';font-size:18px;letter-spacing:.9px;color:var(--mut);font-weight:700;text-transform:uppercase}.kp .n{font-size:32px;font-weight:700;line-height:1.1}.kp .s{font-size:19px;color:var(--mut);font-weight:500}
.row{display:flex;gap:10px}.p{border:1px solid var(--line);border-radius:6px;padding:8px 12px 9px;flex:1;background:#fff;min-width:0}
.t{font-family:'PlexC';font-size:19px;letter-spacing:.8px;color:var(--mut);font-weight:700;text-transform:uppercase;border-bottom:1px solid var(--line);padding-bottom:4px;margin-bottom:6px}
.bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:21px;font-weight:600}.bar .n{width:192px;white-space:nowrap}.bar .tr{flex:1;height:13px;background:var(--soft);border-radius:3px;overflow:hidden}.bar .fi{height:100%}.bar .v{width:54px;text-align:right}
.pend{font-family:'PlexC';font-size:19px;color:#8c97a8;margin-top:6px;font-weight:600;line-height:1.25}
.dots{display:flex;gap:5px;margin:2px 0 6px}.dot{flex:1;height:14px;border-radius:2px}
.lg{display:flex;gap:9px;align-items:flex-start;font-size:20px;line-height:1.2;padding:3px 0;font-weight:600}.lg i{flex:0 0 15px;height:15px;border-radius:50%;margin-top:3px}
.pill{display:inline-block;font-family:'PlexC';font-weight:700;border-radius:4px;padding:2px 12px;font-size:19px;letter-spacing:.8px;background:#fdf1dc;color:var(--a);border:1.5px solid var(--a)}
ul{list-style:none}li{font-size:20px;line-height:1.2;padding:2px 0 2px 15px;position:relative;font-weight:600}li::before{content:"";position:absolute;left:0;top:10px;width:6px;height:6px;background:var(--navy)}li b{font-weight:700}
.bn{border-top:4px solid var(--blue)}.bn h4{font-size:21px;font-weight:700;line-height:1.2;margin-bottom:3px}.bn .d{font-size:20px;line-height:1.25;color:#34425a;font-weight:500}.bn .w{margin-top:5px;font-size:19px;font-weight:600;color:var(--blue);line-height:1.2}
.miss li::before{background:var(--r)}.miss li{font-size:19px}
.foot{font-size:19px;color:var(--mut);font-weight:500;padding-top:2px}
"""
def bars():
    order = [("profitability_margin", "Profitability"), ("growth", "Growth"), ("balance_sheet_cash", "Balance sheet"), ("walk_the_talk", "Walk the talk"), ("promoter_holding_pledge", "Promoter holding"), ("governance_events", "Governance"), ("insider_largeholder", "Insider holders"), ("use_of_funds", "Use of funds"), ("visibility", "Visibility"), ("capex_capacity", "Capex &amp; capacity"), ("product_mix", "Product mix"), ("moat_roadmap", "Moat &amp; roadmap"), ("sector_positioning", "Sector")]
    h = ""
    for k, lab in order:
        if k not in allp: continue
        s, m = allp[k]; pc = 100 * s / m; col = "var(--g)" if pc >= 75 else "var(--a)" if pc >= 50 else "var(--r)"
        h += f'<div class="bar"><div class="n">{lab}</div><div class="tr"><div class="fi" style="width:{pc}%;background:{col}"></div></div><div class="v">{s:g}/{m}</div></div>'
    h += f'<div class="bar"><div class="n" style="color:var(--r)">Risk penalty</div><div class="tr"><div class="fi" style="width:{100*abs(pen)/15}%;background:var(--r)"></div></div><div class="v" style="color:var(--r)">−{abs(pen):g}</div></div>'
    return h + '<div class="pend">Management claims count only when quoted verbatim and audited</div>'
def chart(W=520, H=330):
    mxr = max(rev[l] for l in L8); bw = W / 8; s = f'<svg width="{W}" height="{H+42}" viewBox="0 0 {W} {H+42}">'; pl = []
    for i, l in enumerate(L8):
        h = H * 0.50 * rev[l] / mxr; x = i * bw + 7; y = H - h
        s += f'<rect x="{x}" y="{y}" width="{bw-14}" height="{h}" fill="#c4d0e6"/><text x="{x+(bw-14)/2}" y="{y-5}" text-anchor="middle" font-size="19" font-weight="600" fill="#14213a">{r0(rev[l])}</text><text x="{x+(bw-14)/2}" y="{H+17}" text-anchor="middle" font-size="18" font-weight="600" fill="#5b6b82">{l[:3]}</text><text x="{x+(bw-14)/2}" y="{H+37}" text-anchor="middle" font-size="17" font-weight="500" fill="#8090a6">{l[4:]}</text>'
        pl.append((x + (bw - 14) / 2, H - (H * 0.97) * em[l] / 100))
    s += '<polyline fill="none" stroke="#0e8f63" stroke-width="3" points="' + " ".join(f"{a},{b}" for a, b in pl) + '"/>'
    for (a, b), l in zip(pl, L8): s += f'<circle cx="{a}" cy="{b}" r="4.5" fill="#0e8f63"/><text x="{a}" y="{b-9}" text-anchor="middle" font-size="19" font-weight="700" fill="#0e8f63">{r0(em[l])}%</text>'
    return s + "</svg>"
hd_ = lambda r: datetime.strptime(r["date"], "%d-%b-%Y")
hs = sorted([r for r in HOLD if hd_(r) >= datetime(2024, 6, 1)], key=hd_)
def line_hold(W=296, H_=136):
    vals = [float(r["promoter_pct"]) for r in hs]; lo, hi = min(vals) - 5, max(vals) + 12; n_ = len(vals)
    pt = [(14 + i * (W - 28) / (n_ - 1), H_ - (v - lo) / (hi - lo) * H_) for i, v in enumerate(vals)]
    drops = [(vals[i - 1] - vals[i], i) for i in range(1, n_)]; ki = max(drops)[1] if drops else 2
    s = f'<svg width="{W}" height="{H_+42}" viewBox="0 0 {W} {H_+42}"><polyline fill="none" stroke="#3b5b92" stroke-width="3" points="' + " ".join(f"{a},{b}" for a, b in pt) + '"/>'
    for i, ((a, b), v) in enumerate(zip(pt, vals)):
        s += f'<circle cx="{a}" cy="{b}" r="4" fill="#3b5b92"/>'
        if i in (0, ki, n_ - 1): s += f'<text x="{a+(8 if i==0 else 0)}" y="{b-9}" text-anchor="{"start" if i==0 else "end" if i==n_-1 else "middle"}" font-size="19" font-weight="700" fill="#14213a">{round(v)}%</text>'
    ia = pt[ki]; lab = (COPY.get("holding_note") or {}).get("label", "")
    s += f'<line x1="{ia[0]}" y1="{ia[1]+6}" x2="{ia[0]}" y2="{H_+4}" stroke="#c0392b" stroke-width="1.5" stroke-dasharray="3 3"/><text x="{ia[0]+6}" y="{H_-4}" font-size="17" font-weight="600" fill="#c0392b">{lab}</text>'
    s += f'<text x="0" y="{H_+34}" font-size="17" font-weight="500" fill="#8090a6">{hd_(hs[0]).strftime("%b %y")}</text><text x="{W}" y="{H_+34}" text-anchor="end" font-size="17" font-weight="500" fill="#8090a6">{hd_(hs[-1]).strftime("%b %y")}</text></svg>'
    return s
bk = sorted(BAL, key=lambda k: datetime.strptime(k, "%d-%b-%Y")); b26 = BAL[bk[-1]]
dc = lambda b: ((b.get("borrowings_current") or 0) + (b.get("borrowings_noncurrent") or 0), (b.get("cash") or 0) + (b.get("other_bank_balances") or 0))
bal = [(datetime.strptime(k, "%d-%b-%Y").strftime("%b %y"),) + dc(BAL[k]) for k in bk]
last_q = [l for l in labs if ME(l) <= datetime.strptime(bk[-1], "%d-%b-%Y")]
nq = 2 if datetime.strptime(bk[-1], "%d-%b-%Y").month in (9, 3) else 1
eb = sum(Q[l]["ebitda"] for l in last_q[-nq:]); cfo = b26["cfo_ytd"]; capex = b26["capex_ytd"]; debt, cash = dc(b26)
def cash_bars():
    items = [("EBITDA", eb, "#c4d0e6"), ("Op. cash flow", cfo, "#0e8f63"), ("Capex (cash)", capex, "#b86e00"), ("Free cash flow", cfo - capex, "#c0392b")]
    m = max(abs(x[1]) for x in items); h = ""
    for lab, v, c in items:
        w = max(abs(v) / m * 100, 3); h += f'<div class="bar"><div class="n" style="width:158px;font-size:20px">{lab}</div><div class="tr" style="height:16px"><div class="fi" style="width:{w}%;background:{c}"></div></div><div class="v" style="width:60px">{"−" if v<0 else ""}{r0(abs(v))}</div></div>'
    return h + f'<div class="pend" style="margin-top:4px">H1 FY27 · op. cash {cfo/eb:.1f}x EBITDA</div>'
def debt_cash(W=300, H_=112):
    m = max(max(d, c) for _, d, c in bal); g = (W - 16) / len(bal); s = f'<svg width="{W}" height="{H_+44}" viewBox="0 0 {W} {H_+44}">'
    for i, (lab, d, c) in enumerate(bal):
        x = i * g + 16; bw_ = (g - 14) / 2
        for j, (v, col) in enumerate(((d, "#c0392b"), (c, "#3b5b92"))):
            h_ = H_ * 0.8 * v / m; xx = x + j * bw_; s += f'<rect x="{xx}" y="{H_-h_}" width="{bw_-2}" height="{h_}" fill="{col}"/><text x="{xx+bw_/2-1}" y="{H_-h_-4}" text-anchor="middle" font-size="16" font-weight="600" fill="#14213a">{r0(v)}</text>'
        s += f'<text x="{x+bw_-1}" y="{H_+18}" text-anchor="middle" font-size="17" font-weight="600" fill="#5b6b82">{lab}</text><text x="{x+bw_-1}" y="{H_+38}" text-anchor="middle" font-size="16" font-weight="700" fill="#0e8f63">net {r0(c-d)}</text>'
    return s + "</svg>"
def by_type():
    h = ""
    for (lab, _), (a, b_, c) in zip(CATS, cat_n):
        if a + b_ + c == 0: continue
        seg = "".join(f'<div style="width:{k*26}px;background:{col};height:20px"></div>' for k, col in ((a, "var(--g)"), (b_, "var(--a)"), (c, "var(--r)")) if k)
        h += f'<div class="bar" style="margin:6px 0"><div class="n" style="width:236px;white-space:nowrap;font-size:20px">{lab}</div><div style="display:flex;gap:2px;width:215px">{seg}</div><div style="flex:1;font-size:19px;color:var(--mut);white-space:nowrap;font-weight:600">{a} on time{(" · "+str(b_)+" late") if b_ else ""}{(" · "+str(c)+" missed") if c else ""}</div></div>'
    return h
def qoq(W=330, H_=118):
    ls = L8[-7:]; g = W / len(ls); gr = [100 * (rev[l] / rev[labs[labs.index(l) - 1]] - 1) for l in ls]; m = max(abs(x) for x in gr); s = f'<svg width="{W}" height="{H_+50}" viewBox="0 -18 {W} {H_+50}">'; base = H_ * 0.66
    for i, (l, v) in enumerate(zip(ls, gr)):
        h_ = abs(v) / m * base * 0.82; x = i * g + 6; y = base - h_ if v >= 0 else base
        s += f'<rect x="{x}" y="{y}" width="{g-12}" height="{h_}" fill="{"#0e8f63" if v>=0 else "#c0392b"}"/><text x="{x+(g-12)/2}" y="{(y-5) if v>=0 else (y+h_+17)}" text-anchor="middle" font-size="17" font-weight="700" fill="#14213a">{"−" if v<0 else "+"}{r0(abs(v))}%</text><text x="{x+(g-12)/2}" y="{H_+26}" text-anchor="middle" font-size="17" font-weight="600" fill="#5b6b82">{l[:3]}</text>'
    return s + "</svg>"
dots = "".join(f'<div class="dot" style="background:var(--{c})"></div>' for c, k in [("g", nd), ("a", nl), ("r", nm)] for _ in range(k))
lh = "".join(f'<div class="lg"><i style="background:var(--{r["c"]})"></i><span>{r["t"]}</span></div>' for r in COPY.get("ledger", []))
name = PROF.get("name", SYM).replace(" Limited", "").replace(" Ltd", "")
band = f'EBITDA margin <span>{round(em[cur])}%</span> ({round(em[ya])}% a year ago) on ₹{r0(rev[cur])} Cr revenue. ' + COPY.get("thesis_tail", "")
grade_html = (f'<div class="q ok">{grade}</div><div class="s">{tot:.0f}/100 · {vpct:.0f}% facts verified</div>' if grade else f'<div class="q">?</div><div class="s">Pending · {n_pillars} of 14 pillars · {vpct:.0f}% facts verified (need 80%)</div>')
kp = [("Revenue", f"₹{r0(rev[cur])} Cr", f"₹{r0(rev[ya])} Cr a year ago"), ("EBITDA margin", f"{round(em[cur])}%", f"{round(em[ya])}% a year ago"), ("Net profit", money(Q[cur]["pat"]), f"{money(Q[ya]['pat'])} a year ago"), ("Net cash", money(cash - debt), f"Debt ₹{r0(debt)} Cr"), ("Walk the talk", f"{nd}/{n}", "promises on time")]
kph = "".join(f'<div><div class="l">{a}</div><div class="n">{b}</div><div class="s">{c}</div></div>' for a, b, c in kp)
bn = "".join(f'<div class="p bn"><h4>{x["h"]}</h4><div class="d">{x["d"]}</div><div class="w">{x["w"]}</div></div>' for x in COPY.get("beyond", []))
trust = "".join(f"<li>{t}</li>" for t in COPY.get("trust", [])); und = "".join(f"<li>{t}</li>" for t in COPY.get("undisclosed", []))
wm = "" if FINAL else '<div class="wm">DRAFT · NOT FOR POSTING</div>'
html = f"""<html><head><meta charset=utf-8><style>{CSS}</style></head><body>{wm}
<div class="hd"><div><div class="nm">{name}</div><div class="tk">NSE: {SYM} · {fylabel(cur)} · {COPY.get('tagline','')}</div></div>
<div class="grade"><div class="t">FinGod Quality Grade</div>{grade_html}</div><img class="mark" src="{MARK}"></div>
<div class="band">{band}</div>
<div class="kp">{kph}</div>
<div class="row"><div class="p" style="flex:1.12"><div class="t">Revenue ₹Cr · EBITDA % · Jun-26 on consolidated</div>{chart()}</div><div class="p" style="flex:.88"><div class="t">Pillar scores</div>{bars()}</div></div>
<div class="row"><div class="p"><div class="t">Promoter holding %</div>{line_hold()}</div><div class="p"><div class="t">Cash conversion · ₹Cr</div>{cash_bars()}</div><div class="p"><div class="t">Debt vs cash · ₹Cr</div>{debt_cash()}</div></div>
<div class="row"><div class="p" style="flex:1.12"><div class="t">Walk the talk · {n} checkable promises since Nov-23</div><div class="dots">{dots}</div><div style="font-size:19px;font-weight:700;margin-bottom:3px">{nd} on time · {nl} late · {nm} missed · {len(unk)} not verifiable</div>{lh}</div>
<div class="p" style="flex:.88"><div class="t">Trust gate</div><span class="pill">{gate.replace('-', ' · ')}</span><ul style="margin-top:4px">{trust}</ul></div></div>
<div class="row"><div class="p" style="flex:1.5"><div class="t">Promises by type · on time / late / missed</div>{by_type()}<div class="pend">{COPY.get('pattern','')}</div></div><div class="p"><div class="t">QoQ revenue growth % · Jun-26 consol.</div>{qoq()}</div></div>
<div class="row">{bn}</div>
<div class="p miss"><div class="t" style="color:var(--r)">Not disclosed · checked {COPY.get('undisclosed_src','')}</div><ul style="display:grid;grid-template-columns:1fr 1fr;column-gap:16px">{und}</ul></div>
<div class="foot">Delays up to 3 months count as on time. Source: company filings (NSE/BSE). For educational purpose only.</div></body></html>"""
out = os.path.join(ROOT, "cards", SYM); os.makedirs(out, exist_ok=True)
open(os.path.join(out, "card.html"), "w").write(html)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1200}, device_scale_factor=2)
        pg.goto("file://" + os.path.join(out, "card.html")); pg.wait_for_timeout(700)
        h = pg.evaluate("document.body.scrollHeight"); pg.screenshot(path=os.path.join(out, "card.png"), clip={"x": 0, "y": 0, "width": 1080, "height": h}, full_page=True); b.close()
    print("card.png", 1080 * 2, "x", h * 2, "| css height", h, "| walk", f"{nd}/{n}", "late", nl, "missed", nm, "| facts", f"{nfacts}/{next_}", "| grade", grade or "pending")
except Exception as e:
    print("render failed:", type(e).__name__, str(e)[:200])
