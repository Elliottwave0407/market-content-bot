"""Banks and insurers: result cards from NSE's XBRL filings (their BSE tables / PDFs do not fit the normal reader).
Bank: net total income / pre-provision profit / PAT. Life insurer: net premium / profit before tax / PAT. General insurer: net premium earned / PBT / PAT. (fin_data._special, quarter_rating.KIND_PARAMS)
Poll-loop hook (tick) runs only when FIN_LIVE=1; dry run by day via the fin-results-test workflow (FIN_DAY). While live, the BSE route waits YIELD_H hours for this one."""
import os, sys, json, re, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p
import card, tags, fin_data as fd, nse_results as nse
ST = "state/fin_results.json"
OUTDIR = os.environ.get("OUT_DIR", "out")
SEND = os.environ.get("POLL_SEND", os.environ.get("FIN_SEND", "0")) == "1"
LIVE = os.environ.get("FIN_LIVE", "0") == "1"
YIELD_H = 6          # hours the BSE route waits for this route before it may post its own card
BANKS = set("HDFCBANK ICICIBANK SBIN KOTAKBANK AXISBANK INDUSINDBK FEDERALBNK IDFCFIRSTB BANKBARODA PNB CANBK UNIONBANK BANDHANBNK AUBANK YESBANK RBLBANK INDIANB MAHABANK CENTRALBK UCOBANK IOB KARURVYSYA CUB SOUTHBANK TMB DCBBANK CSBBANK J&KBANK KTKBANK EQUITASBNK UJJIVANSFB IDBI BANKINDIA PSB DHANBANK ESAFSFB UTKARSHBNK SURYODAY CAPITALSFB".split())
INSURERS = set("HDFCLIFE SBILIFE ICICIPRULI LICI ICICIGI NIACL GICRE STARHEALTH GODIGIT NIVABUPA".split())
FINSYMS = BANKS | INSURERS
_S = {"last_tick": 0.0, "scan_at": 0.0, "rows": [], "c2s": None}
TRY = {}
LABEL = {"bank": "Net total income", "life": "Net premium", "general": "Net premium earned"}

def is_fin_code(code):
    """True if this BSE scrip code is a bank/insurer handled by this route (only while FIN_LIVE=1)."""
    try:
        if _S["c2s"] is None:
            _S["c2s"] = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "symbols.json")))["m"]
        return LIVE and _S["c2s"].get(str(code).strip(), "").upper() in FINSYMS
    except Exception:
        return False

def load():
    try: return json.load(open(ST))
    except Exception: return {"posted": [], "done": []}

def save(st):
    os.makedirs("state", exist_ok=True)
    st["done"] = st["done"][-2000:]; st["posted"] = st["posted"][-1000:]
    json.dump(st, open(ST, "w"))

def qe_for(filed):
    """Quarter end a filing on this date reports: the latest quarter end before it (Oct 22 -> 30 Sep)."""
    m, y = filed.month, filed.year
    qm = max([q for q in (3, 6, 9, 12) if q < m] or [12])
    qy = y if qm < m else y - 1
    return datetime(qy, qm, 31 if qm in (3, 12) else 30)

def sh(d, m):
    y, mm = divmod(d.year * 12 + d.month - 1 - m, 12); mm += 1
    return datetime(y, mm, 31 if mm in (1, 3, 5, 7, 8, 10, 12) else 30 if mm != 2 else 28)

def listing(s, sym):
    """-> list of dict(qe, basis, url, when) of financial-results XBRL filings on NSE (integrated + legacy)."""
    out = []
    def get(url, params, ref):
        for k in range(3):
            try:
                r = s.get(url, params=params, headers=ref, timeout=40); return r.json()
            except Exception:
                nse._S["sess"] = None; time.sleep(2)
        return None
    d = get("https://www.nseindia.com/api/integrated-filing-results", {"index": "equities", "symbol": sym}, fd.REF_I)
    for x in ((d or {}).get("data", []) if isinstance(d, dict) else []):
        if "Financial" in (x.get("type") or "") and x.get("xbrl") not in (None, "None"):
            qe = fd._dt(x.get("qe_Date"))
            if qe: out.append({"qe": qe, "basis": "consolidated" if x.get("consolidated") == "Consolidated" else "standalone", "url": x["xbrl"], "when": (x.get("creation_Date") or "")[:11]})
    d = get("https://www.nseindia.com/api/corporates-financial-results", {"index": "equities", "symbol": sym, "period": "Quarterly"}, fd.REF_L)
    for x in (d if isinstance(d, list) else []):
        if x.get("xbrl") and x.get("cumulative") in (None, "Non-cumulative"):
            qe = fd._dt(x.get("toDate"))
            if qe: out.append({"qe": qe, "basis": "consolidated" if x.get("consolidated") == "Consolidated" else "standalone", "url": x["xbrl"], "when": (x.get("filingDate") or "")[:11]})
    return out

def parse(s, f):
    for k in range(3):
        try:
            t = s.get(f["url"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
            return fd.parse_xbrl(t)
        except Exception:
            nse._S["sess"] = None; time.sleep(2)
    return None

def to_card(m):
    if not m: return {}
    return {"revenue": m["revenue"] * 10, "ebitda": None if m.get("ebitda") is None else m["ebitda"] * 10, "pbt": (m.get("pbt") or 0) * 10, "pat": None if m.get("pat") is None else m["pat"] * 10, "eps": m.get("eps"), "bank": False, "kind": m.get("kind")}

def build(sym, name, link, st, final=False, filed=None):
    """-> ('done', caption, png, key) / ('wait', reason) / ('skip', reason)"""
    s = nse.sess()
    rows = listing(s, sym)
    if not rows: return ("wait", "no XBRL listing yet")
    # newest quarter that has an XBRL filing; a quarter must exist on one basis for current, quarter-ago and year-ago
    want = qe_for(filed) if filed else None      # only the quarter this filing reports: never post an older quarter because the new one's XBRL is not out yet
    for T in sorted({r["qe"] for r in rows}, reverse=True)[:2]:
        if want is not None and T != want: continue
        if f"{sym}|{T:%Y-%m-%d}" in st["posted"]: return ("skip", "already posted")
        for basis in ("consolidated", "standalone"):
            def get(d):
                c = [r for r in rows if r["qe"] == d and r["basis"] == basis]
                if not c: return None
                return parse(s, max(c, key=lambda r: r["when"] or ""))
            cur, prev, yago = get(T), get(sh(T, 3)), get(sh(T, 12))
            if not (cur and prev and yago and cur.get("kind") and cur.get("kind") == prev.get("kind") == yago.get("kind")): continue
            q2, q3, yprev = get(sh(T, 6)), get(sh(T, 9)), get(sh(T, 15))
            ql = T.strftime("%b-%y")
            qs = [{"q": ql, "m": to_card(cur)}, {"q": sh(T, 3).strftime("%b-%y"), "m": to_card(prev)}, {"q": sh(T, 6).strftime("%b-%y"), "m": to_card(q2)}, {"q": sh(T, 9).strftime("%b-%y"), "m": to_card(q3)}, {"q": sh(T, 12).strftime("%b-%y"), "m": to_card(yago)}]
            os.makedirs(OUTDIR, exist_ok=True)
            png = os.path.join(OUTDIR, f"fin_{sym}_{ql}_{basis}.png")
            v = card.render(name, f"NSE {sym}", basis, qs, png, yprev=to_card(yprev) if yprev else None)
            rv, pt = card.cr(qs[0]["m"]["revenue"]), card.cr(qs[0]["m"]["pat"])
            ry = card.fmt_pct(card.pct(qs[0]["m"]["revenue"], qs[4]["m"]["revenue"])); py = card.fmt_pct(card.pct(qs[0]["m"]["pat"], qs[4]["m"]["pat"]))
            dd = lambda x: 0 if x and abs(x) >= 100 else 1
            cap = (f"{name} {nse.fy_label(ql)} | {basis.capitalize()}\n"
                   f"{LABEL[cur['kind']]} Rs {card.fmt_num(rv, dd(rv))} Cr ({ry} YoY), net profit Rs {card.fmt_num(pt, dd(pt))} Cr ({py} YoY).\n"
                   f"Filing: {link}\n\n{nse.DISC}")
            return ("done", cap, png, f"{sym}|{T:%Y-%m-%d}|{basis}|{v}")
    return ("wait", "XBRL for the quarter, quarter-ago and year-ago not all available yet")

BANK_PROMPT = """You are reading an Indian BANK's quarterly financial results filing (PDF). Return ONLY JSON:
{"unit":"lakh|crore|million|thousand|actual",
 "quarter_end_columns":["<current quarter end date>","<previous quarter end date>","<year-ago quarter end date>"],
 "consolidated": {"interest_earned":[c,p,y],"other_income":[c,p,y],"total_income":[c,p,y],"interest_expended":[c,p,y],"operating_expenses":[c,p,y],"ppop":[c,p,y],"provisions":[c,p,y],"pbt":[c,p,y],"tax":[c,p,y],"pat":[c,p,y],"eps":[c,p,y]} or null,
 "standalone": {same keys} or null}
Rules: c = current quarter, p = immediately preceding quarter, y = same quarter last year (the first three numeric columns; ignore nine-month, half-year and full-year columns).
interest_earned = 'Interest earned' (total of the interest lines). total_income = 'Total income' (interest earned + other income). interest_expended = 'Interest expended'. operating_expenses = 'Operating expenses'.
ppop = 'Operating profit before provisions and contingencies'. provisions = provisions and contingencies (other than tax). pbt = profit before tax. pat = net profit for the period after minority interest / share of associates if shown, else net profit after tax. eps = basic EPS.
Numbers exactly as printed, in the printed unit; negatives for losses. Use null for any value not present. Do not compute or guess."""
PDFTRY = {}

def _bank_pdf(x):
    """Download the NSE filing PDF (quick retries: NSE's CDN sometimes answers 200 with an empty body right after a filing)."""
    for att in range(4):
        try:
            u = x["attchmntFile"] + ("" if att == 0 else f"?cb={int(time.time() * 1000)}")
            r = nse.sess().get(u, headers={"Referer": nse.REF}, timeout=60)
            if r.content[:4] == b"%PDF" and len(r.content) < 15_000_000: return r.content
        except Exception: pass
        time.sleep(1.5)
    return None

def build_pdf(sym, name, x, st):
    """Banks only: read the NSE filing PDF at once (the XBRL lags by minutes to hours). The current column must pass the bank arithmetic AND the
    previous / year-ago columns must match NSE's filed XBRL history, otherwise nothing is posted here and the XBRL route follows. -> same tuples as build()."""
    import gemini_read as gr, pdf_card as pc
    from concurrent.futures import ThreadPoolExecutor
    if sym not in BANKS: return ("skip", "not a bank")
    sid = str(x.get("seq_id"))
    if PDFTRY.get(sid, 0) >= 3: return ("wait", "pdf attempts used")
    PDFTRY[sid] = PDFTRY.get(sid, 0) + 1
    content = _bank_pdf(x)
    if not content: return ("wait", "pdf not downloadable yet")
    out, err = gr.read_pdf(pc.geminikey(), pc.MODEL, pc.trim_pdf(content), tries=2, timeout=120, prompt=BANK_PROMPT)
    if out is None: return ("wait", f"pdf read failed: {str(err)[:60]}")
    k = pc.K.get(str(out.get("unit", "")).lower()); cols = out.get("quarter_end_columns") or []
    qe = pc.parse_qend(cols[0]) if cols else None
    if not k or qe is None: return ("wait", "unit or quarter not readable")
    ms = [(lambda q_: q_[0] * 12 + q_[1] if q_ else None)(pc.parse_qend(c)) for c in cols[:3]]
    if len(ms) == 3 and None not in ms and (ms[0] - ms[1], ms[0] - ms[2]) not in ((3, 12), (12, 3)): return ("wait", "not a quarterly layout")
    if len(ms) == 3 and None not in ms and (ms[0] - ms[1]) >= 9:      # columns listed current | year-ago | previous: swap
        for b_ in ("consolidated", "standalone"):
            d_ = out.get(b_)
            if isinstance(d_, dict):
                for kk, vv in list(d_.items()):
                    if isinstance(vv, list) and len(vv) >= 3: vv[1], vv[2] = vv[2], vv[1]
    T = datetime(qe[0], qe[1], 31 if qe[1] in (1, 3, 5, 7, 8, 10, 12) else 30)
    if f"{sym}|{T:%Y-%m-%d}" in st["posted"] and not os.environ.get("FIN_FORCE_PDF"): return ("skip", "already posted")
    s = nse.sess(); rows = listing(s, sym)
    cr = lambda v: None if v is None else v * k / 10.0      # printed unit -> Rs crore
    near = lambda a, b, tol=0.005, floor=0.5: a is not None and b is not None and abs(a - b) <= max(floor, tol * abs(b))
    for basis in ("consolidated", "standalone"):
        d = out.get(basis)
        if not isinstance(d, dict): continue
        v = lambda key, i: pc.val(d, key, i)
        p(f"  [bank pdf] {sym} {basis} cols={cols[:3]} unit={out.get('unit')} " + ", ".join(f"{kk}={d.get(kk)}" for kk in ("total_income", "interest_expended", "operating_expenses", "ppop", "provisions", "pbt", "pat")))
        if None in (v("total_income", 0), v("interest_expended", 0), v("operating_expenses", 0), v("ppop", 0), v("provisions", 0), v("pbt", 0), v("pat", 0)): p(f"  {sym} {basis}: a required line is missing - not used"); continue
        if basis == "standalone" and isinstance(out.get("consolidated"), dict) and pc.val(out["consolidated"], "pat", 0) is not None: return ("wait", "consolidated present but failed checks")
        oi, opx, prov = v("total_income", 0) - v("interest_expended", 0) - (v("operating_expenses", 0) or 0), None, v("provisions", 0)
        tolx = lambda a, b: abs(a - b) <= max(1.5, 0.003 * max(abs(a), abs(b)))
        if v("operating_expenses", 0) is not None and not tolx(oi, v("ppop", 0)): p(f"  {sym} {basis}: operating profit arithmetic failed"); continue
        if prov is not None and not tolx(v("ppop", 0) - prov, v("pbt", 0)): p(f"  {sym} {basis}: PBT arithmetic failed"); continue
        def get(dd):
            c = [r for r in rows if r["qe"] == dd and r["basis"] == basis]
            return parse(s, max(c, key=lambda r: r["when"] or "")) if c else None
        dates = [sh(T, 3), sh(T, 12), sh(T, 6), sh(T, 9), sh(T, 15)]
        with ThreadPoolExecutor(max_workers=5) as ex: prev, yago, q2, q3, yprev = list(ex.map(get, dates))
        if not (prev and yago and prev.get("kind") == yago.get("kind") == "bank"): continue
        ok = True
        cur_rev = cr(v("total_income", 0) - v("interest_expended", 0))
        if not (prev.get("revenue") and 0.65 <= cur_rev / prev["revenue"] <= 1.5):      # a bank's net total income does not double or halve in a quarter: that is a cumulative (half-year / nine-month) column
            p(f"  {sym} {basis}: current net total income {cur_rev} vs previous quarter {prev.get('revenue')} - looks like a cumulative column, withheld"); continue
        for i, m_ in ((1, prev), (2, yago)):      # the PDF's own previous / year-ago columns must equal NSE's filed history
            rev_i = cr(None if v("total_income", i) is None or v("interest_expended", i) is None else v("total_income", i) - v("interest_expended", i))
            if not (near(rev_i, m_["revenue"]) and near(cr(v("ppop", i)), m_["ebitda"], 0.01, 1.0) and near(cr(v("pat", i)), m_["pat"], 0.03, 1.0)): ok = False
        if not ok: p(f"  {sym} {basis}: previous/year-ago columns differ from NSE XBRL history"); continue
        cur = {"revenue": cr(v("total_income", 0) - v("interest_expended", 0)), "ebitda": cr(v("ppop", 0)), "pbt": cr(v("pbt", 0)), "pat": cr(v("pat", 0)), "eps": v("eps", 0), "kind": "bank"}
        ql = T.strftime("%b-%y")
        qs = [{"q": ql, "m": to_card(cur)}, {"q": sh(T, 3).strftime("%b-%y"), "m": to_card(prev)}, {"q": sh(T, 6).strftime("%b-%y"), "m": to_card(q2)}, {"q": sh(T, 9).strftime("%b-%y"), "m": to_card(q3)}, {"q": sh(T, 12).strftime("%b-%y"), "m": to_card(yago)}]
        os.makedirs(OUTDIR, exist_ok=True)
        png = os.path.join(OUTDIR, f"fin_{sym}_{ql}_{basis}.png")
        vd = card.render(name, f"NSE {sym}", basis, qs, png, yprev=to_card(yprev) if yprev else None)
        rv, pt = card.cr(qs[0]["m"]["revenue"]), card.cr(qs[0]["m"]["pat"])
        ry = card.fmt_pct(card.pct(qs[0]["m"]["revenue"], qs[4]["m"]["revenue"])); py = card.fmt_pct(card.pct(qs[0]["m"]["pat"], qs[4]["m"]["pat"]))
        dd = lambda z: 0 if z and abs(z) >= 100 else 1
        cap = (f"{name} {nse.fy_label(ql)} | {basis.capitalize()}\n"
               f"{LABEL['bank']} Rs {card.fmt_num(rv, dd(rv))} Cr ({ry} YoY), net profit Rs {card.fmt_num(pt, dd(pt))} Cr ({py} YoY).\n"
               f"Filing: {x.get('attchmntFile')}\n\n{nse.DISC}")
        return ("done", cap, png, f"{sym}|{T:%Y-%m-%d}|{basis}|{vd}")
    return ("wait", "pdf figures did not pass the checks")

def run_once(day=None, maxn=1):
    now = datetime.now(nse.IST)
    st = load(); changed = False
    if day or time.time() - _S["scan_at"] > int(os.environ.get("FIN_SCAN_S", "20")):
        days = [day] if day else [now] + ([now - timedelta(days=1)] if now.hour < 3 else [])
        rows = []
        for d in days: rows += nse.result_rows(nse.fetch_day(d))
        _S["rows"] = [x for x in rows if (x.get("symbol") or "").upper() in FINSYMS]; _S["scan_at"] = time.time()
        p(f"bank/insurer result filings in window: {len(_S['rows'])}")
    n = 0
    for x in _S["rows"]:
        sym = x["symbol"].upper(); sid = str(x.get("seq_id"))
        if sid in st["done"] and not os.environ.get("FIN_FORCE_PDF"): continue
        if TRY.get(sid, (0, 0))[0] >= 120 or time.time() - TRY.get(sid, (0, 0))[1] < int(os.environ.get("FIN_RETRY_S", "45")): continue
        TRY[sid] = (TRY.get(sid, (0, 0))[0] + 1, time.time())
        name = (x.get("sm_name") or sym).strip()
        out = ((build_pdf(sym, name, x, st) if sym in BANKS else None) or ("wait", ""))
        if out[0] not in ("done", "skip"): out = build(sym, name, x.get("attchmntFile") or "", st, filed=nse.parse_dt(x))
        if out[0] == "skip": st["done"].append(sid); changed = True; continue
        if out[0] == "wait": p(f"  {sym}: not ready - {out[1]}"); continue
        _, cap, png, key = out
        sym_, T, basis, verdict = key.split("|")
        p(f"  [fin card] {sym} {T} {basis} verdict={verdict} :: {cap.splitlines()[1]}")
        tweet = "\n".join(cap.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(symbol=sym, name=name), tags.quarter_tag(datetime.strptime(T, "%Y-%m-%d").strftime("%b-%y")), "#Results")
        if SEND and nse.CHAT:
            import xbuttons
            cc, flink = xbuttons.split_link(cap)
            with open(png, "rb") as fh:
                rs = nse.tg("sendPhoto", data={"chat_id": nse.CHAT, "caption": cc[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
            p(f"  sent ok={rs.get('ok')}")
            if not rs.get("ok"): continue
            try:
                import results_poller as _rp; _rp.mirror_to_channel(png, cc, flink, key, force=True)
            except Exception as _e:
                p("  channel copy failed:", type(_e).__name__)
            import store; store.log_result("fin", cap, rs, card.LAST, x.get("an_dt") and datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S"))
            time.sleep(3.2)
        st["posted"].append(f"{sym}|{T}"); st["done"].append(sid); changed = True
        try:      # tell the BSE route this company/quarter is posted
            c2s = _S["c2s"] or {}
            code = next((c for c, sy in c2s.items() if sy.upper() == sym), None)
            if code: nse._mark_seen(f"{code}|{datetime.strptime(T, '%Y-%m-%d').strftime('%b-%y')}|{basis}")
        except Exception: pass
        n += 1
        if n >= maxn: break
    if changed and (SEND or not day): save(st)
    return changed

def tick():
    """Poll-loop hook. Returns (changed, lines). Never raises. Only when FIN_LIVE=1 and posting is on."""
    if not (LIVE and SEND and nse.CHAT) or time.time() - _S["last_tick"] < int(os.environ.get("FIN_TICK_S", "10")): return False, []
    _S["last_tick"] = time.time()
    import ci_out
    n0 = len(ci_out.OUT)
    try: ch = run_once(maxn=1)
    except Exception as e:
        p("fin results ERROR:", repr(e)[:200].replace(nse.TOKEN, "<token>") if nse.TOKEN else repr(e)[:200]); ch = False
    return ch, ci_out.OUT[n0:]

if __name__ == "__main__":
    from ci_out import publish
    d = os.environ.get("FIN_DAY", "").strip()
    is_fin_code("0")      # loads the code->symbol map
    try: run_once(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=nse.IST) if d else None, maxn=int(os.environ.get("FIN_MAX", "6")))
    except Exception:
        import traceback; p("ERROR", traceback.format_exc()[-900:])
    publish()
