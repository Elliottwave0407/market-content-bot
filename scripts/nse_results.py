"""NSE-only results source. BSE-listed companies are handled by results_poller; this covers companies listed on NSE but not on BSE.
Detects result filings from NSE's announcements feed, reads the PDF with Gemini, applies strict arithmetic checks (there is no BSE history to cross-check),
renders the usual result card and posts it to the Results Corner. Dry run unless NSE_SEND=1.
Env: NSE_SEND, NSE_ONLY (symbols, comma separated, test mode), NSE_DAY (YYYY-MM-DD, test mode), PDF_TRIES."""
import os, sys, re, json, time, tempfile
from datetime import datetime, timedelta, timezone
import requests
sys.path.insert(0, os.path.dirname(__file__))
import gemini_read as gr
import pdf_card as pc
import results_fetcher as rf
import card, tags
from ci_out import p

IST = timezone(timedelta(hours=5, minutes=30))
ST = "state/nse_results.json"
OUTDIR = os.environ.get("OUT_DIR", "out")
SEND = os.environ.get("NSE_SEND", "0") == "1"
ONLY = [x.strip().upper() for x in os.environ.get("NSE_ONLY", "").split(",") if x.strip()]
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DISC = "For educational purpose only."
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
DESCS = ("outcome of board meeting", "financial results", "updates")
RES_RX = re.compile(r"financial results|results for the (quarter|period|half|year)|(un)?audited .*results", re.I)
NOT_RX = re.compile(r"earnings call|conference call|investor meet|newspaper|press release|presentation", re.I)
MAX_AGE_H = 36
FINAL_H = 24
_S = {"sess": None, "at": 0.0, "bse": None, "bse_at": 0.0, "last_tick": 0.0}
TRY_AT, TRIES = {}, {}

def load():
    try:
        return json.load(open(ST))
    except Exception:
        return {"posted": [], "done": [], "init": False}

def save(st):
    os.makedirs("state", exist_ok=True)
    st["done"] = st["done"][-3000:]
    st["posted"] = st["posted"][-1500:]
    json.dump(st, open(ST, "w"))

def sess():
    if _S["sess"] is None or time.time() - _S["at"] > 1200:
        s = requests.Session()
        s.headers.update(UA)
        s.get("https://www.nseindia.com/", timeout=25)
        s.get(REF, timeout=25)
        _S["sess"], _S["at"] = s, time.time()
    return _S["sess"]

def fetch_day(day):
    ds = day.strftime("%d-%m-%Y")
    for k in range(3):
        try:
            r = sess().get(f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={ds}&to_date={ds}", headers={"Referer": REF}, timeout=40)
            if r.status_code == 200:
                return r.json() if r.text.strip() else []
            p("nse announcements HTTP", r.status_code)
        except Exception as e:
            p("nse announcements error", repr(e)[:80])
        _S["sess"] = None
        time.sleep(3)
    return []

def bse_isins():
    """ISINs listed on BSE (all groups), refreshed every 12 h."""
    if _S["bse"] is not None and time.time() - _S["bse_at"] < 12 * 3600:
        return _S["bse"]
    from bse import BSE
    out = set()
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y"):
            try:
                for x in b.listSecurities(group=g):
                    if x.get("ISIN_NUMBER"):
                        out.add(x["ISIN_NUMBER"].strip())
            except Exception:
                continue
    if len(out) > 1000:
        _S["bse"], _S["bse_at"] = out, time.time()
    p("BSE ISINs known:", len(out))
    return out if len(out) > 1000 else None

def result_rows(rows):
    out = []
    for x in rows:
        if (x.get("desc") or "").strip().lower() not in DESCS:
            continue
        t = x.get("attchmntText") or ""
        if RES_RX.search(t) and not NOT_RX.search(t) and x.get("attchmntFile", "").lower().endswith(".pdf"):
            out.append(x)
    return out

def parse_dt(x):
    try:
        return datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    except Exception:
        return None

def arith_col(d, i):
    ti, ex, pbt, tax, pat = (pc.val(d, x, i) for x in ("total_income", "total_expenses", "pbt", "tax", "pat"))
    tol = lambda a, b: abs(a - b) <= max(1.5, 0.002 * max(abs(a), abs(b)))
    res = []
    if None not in (ti, ex, pbt): res.append(tol(ti - ex, pbt))
    if None not in (pbt, tax, pat): res.append(tol(pbt - tax, pat))
    return bool(res) and all(res)

def read_card(content, name):
    """-> (dict(basis, q, quarters) or None, reason)"""
    key = pc.geminikey()
    out, err = gr.read_pdf(key, pc.MODEL, content, tries=int(os.environ.get("PDF_TRIES", "2")), timeout=120)
    if out is None:
        return None, f"pdf read failed: {str(err)[:70]}"
    k = pc.K.get(str(out.get("unit", "")).lower())
    cols = out.get("quarter_end_columns") or []
    qe = pc.parse_qend(cols[0]) if cols else None
    if not k or qe is None:
        return None, "unit or quarter not readable"
    try:
        ms = []
        for c in cols[:3]:
            pq = pc.parse_qend(c)
            ms.append(pq[0] * 12 + pq[1] if pq else None)
        if len(ms) == 3 and None not in ms and (ms[0] - ms[1]) >= 9 and 1 <= (ms[0] - ms[2]) <= 5:
            for b_ in ("consolidated", "standalone"):
                d_ = out.get(b_)
                if isinstance(d_, dict):
                    for kk, vv in list(d_.items()):
                        if isinstance(vv, list) and len(vv) >= 3:
                            vv[1], vv[2] = vv[2], vv[1]
    except Exception:
        pass
    q = rf.qcode(qe[0], qe[1])
    cons = out.get("consolidated")
    has_cons = isinstance(cons, dict) and pc.val(cons, "revenue", 0) is not None and pc.val(cons, "pat", 0) is not None
    order = ("consolidated", "standalone") if has_cons else ("standalone",)
    for basis in order:
        d = out.get(basis)
        if not isinstance(d, dict) or pc.val(d, "revenue", 0) is None or pc.val(d, "pat", 0) is None:
            continue
        oks = [arith_col(d, i) for i in range(3)]
        p(f"  {name} {basis} arithmetic by column (current, previous, year-ago): {oks}")
        if not (oks[0] and oks[1] and oks[2]):
            return None, f"{basis} figures failed arithmetic checks"
        cur, prev, yago = (pc.to_m(d, i, k) for i in range(3))
        r0, r1 = cur["revenue"], prev["revenue"]
        if r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50):
            return None, "figures inconsistent with previous quarter"
        rv0, fc0 = pc.val(d, "revenue", 0), pc.val(d, "finance_costs", 0)
        fin_heavy = bool(rv0 and fc0 is not None and fc0 / rv0 >= 0.25)
        need = ("revenue", "pat", "eps") + (() if fin_heavy else ("ebitda",))
        miss = sorted({kk for m_ in (cur, prev, yago) for kk in need if m_.get(kk) is None})
        if miss:
            return None, f"missing {miss}"
        empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
        quarters = [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 1), "m": prev}, {"q": rf.qlabel(q - 2), "m": empty}, {"q": rf.qlabel(q - 3), "m": empty}, {"q": rf.qlabel(q - 4), "m": yago}]
        return {"basis": basis, "q": q, "quarters": quarters}, "ok"
    return None, "no usable statement"

def fy_label(ql):
    try:
        d = datetime.strptime(ql, "%b-%y")
        qn = {6: 1, 9: 2, 12: 3, 3: 4}[d.month]
        fy = d.year + (1 if d.month > 3 else 0)
        return f"Q{qn} FY{str(fy)[2:]}"
    except Exception:
        return ql

def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", timeout=60, **kw)
    try:
        return r.json()
    except Exception:
        return {"ok": False}

def post_card(x, res, png, ql):
    name = (x.get("sm_name") or x["symbol"]).strip()
    sym = x["symbol"]
    cur, yago = res["quarters"][0]["m"], res["quarters"][4]["m"]
    sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
    sd = 0 if sales and sales >= 100 else 1
    pd_ = 0 if pat and pat >= 100 else 1
    sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
    lk = x["attchmntFile"]
    cap = (f"{name} {fy_label(ql)} | {res['basis'].capitalize()}\n"
           f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
           f"Read from the filing PDF (NSE; arithmetic-checked). Filing: {lk}\n\n{DISC}")
    tweet = "\n".join(cap.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(symbol=sym, name=name), tags.quarter_tag(ql), "#Results")
    return cap, tweet

def process(x, st, final):
    sym, isin = x["symbol"], x.get("sm_isin") or ""
    sid = str(x.get("seq_id"))
    name = (x.get("sm_name") or sym).strip()
    if TRIES.get(sid, 0) >= 8 or time.time() - TRY_AT.get(sid, 0) < 240:
        return "skip"
    TRY_AT[sid] = time.time()
    TRIES[sid] = TRIES.get(sid, 0) + 1
    try:
        r = sess().get(x["attchmntFile"], headers={"Referer": REF}, timeout=60)
    except Exception as e:
        p(f"  {sym}: download error {repr(e)[:60]}")
        return "wait"
    if r.content[:4] != b"%PDF" or len(r.content) > 15_000_000:
        p(f"  {sym}: file is not a readable PDF ({r.status_code}, {len(r.content)} bytes)")
        return "wait"
    res, why = read_card(r.content, name)
    if res is None:
        p(f"  {sym}: not postable yet - {why}")
        return "wait" if not final else "stub:" + why
    ql = rf.qlabel(res["q"])
    key = f"NSE|{isin or sym}|{ql}|{res['basis']}"
    if key in st["posted"] and not ONLY:
        p(f"  dup skip {key}")
        return "done"
    os.makedirs(OUTDIR, exist_ok=True)
    png = os.path.join(OUTDIR, f"nse_{sym}_{ql}_{res['basis']}.png")
    card.render(name, f"NSE {sym}", res["basis"], res["quarters"], png, filed_note="Read from the filing PDF; arithmetic-checked.")
    cap, tweet = post_card(x, res, png, ql)
    p(f"  [card] {key} :: {cap.splitlines()[1]}")
    if SEND and CHAT:
        import xbuttons
        cc, flink = xbuttons.split_link(cap)
        with open(png, "rb") as fh:
            rr = tg("sendPhoto", data={"chat_id": CHAT, "caption": cc[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
        p(f"  sent ok={rr.get('ok')}")
        if not rr.get("ok"):
            return "wait"
        time.sleep(3.2)
    if not ONLY:
        st["posted"].append(key)
    return "done"

def run_once(day=None):
    """One pass. Returns True if state changed."""
    st = load()
    now = datetime.now(IST)
    days = [day] if day else [now] + ([now - timedelta(days=1)] if now.hour < 3 else [])
    rows = []
    for d in days:
        rows += result_rows(fetch_day(d))
    bse = bse_isins()
    if bse is None:
        p("BSE ISIN list unavailable - skipping this pass")
        return False
    todo = []
    for x in rows:
        sid = str(x.get("seq_id"))
        isin = (x.get("sm_isin") or "").strip()
        if not isin or isin in bse:
            continue
        if ONLY and x["symbol"].upper() not in ONLY:
            continue
        if not ONLY and sid in st["done"]:
            continue
        todo.append(x)
    if not st.get("init") and not ONLY:
        for x in todo:
            dt = parse_dt(x)
            if dt is None or now - dt > timedelta(hours=3):
                st["done"].append(str(x.get("seq_id")))
        st["init"] = True
        save(st)
        p(f"NSE results baseline set ({len(todo)} NSE-only result filings seen)")
        return True
    p(f"NSE result filings today: {len(rows)}, NSE-only to process: {len(todo)}")
    changed = False
    n = 0
    for x in todo:
        dt = parse_dt(x)
        age_h = (now - dt).total_seconds() / 3600 if dt else 0
        if age_h > MAX_AGE_H and not ONLY:
            st["done"].append(str(x.get("seq_id")))
            changed = True
            continue
        if n >= 3:
            break
        out = process(x, st, final=age_h >= FINAL_H)
        if out == "skip":
            continue
        n += 1
        if out == "done":
            st["done"].append(str(x.get("seq_id")))
            changed = True
        elif out.startswith("stub:"):
            p(f"  {x['symbol']}: posting 'numbers not shown' card ({out[5:]})")
            if SEND and CHAT:
                png = os.path.join(OUTDIR, f"nse_stub_{x['symbol']}.png")
                os.makedirs(OUTDIR, exist_ok=True)
                card.render_stub((x.get("sm_name") or x["symbol"]).strip(), f"NSE {x['symbol']}", "Results", out[5:], png)
                with open(png, "rb") as fh:
                    tg("sendPhoto", data={"chat_id": CHAT, "caption": f"{(x.get('sm_name') or x['symbol']).strip()} results filed. Numbers not shown ({out[5:]}).\nFiling: {x['attchmntFile']}\n\n{DISC}"}, files={"photo": fh})
            st["done"].append(str(x.get("seq_id")))
            changed = True
    if changed and SEND and not ONLY:
        save(st)
    for line in pc.LOG:
        p("[pdf]", line)
    pc.LOG.clear()
    return changed

def tick():
    """Called by the poll loop (live only). Every ~60 s. Returns (changed, lines)."""
    if not (SEND and CHAT) or time.time() - _S["last_tick"] < 60:
        return False, []
    _S["last_tick"] = time.time()
    import ci_out
    n0 = len(ci_out.OUT)
    try:
        ch = run_once()
    except Exception as e:
        p("nse results ERROR:", repr(e)[:200].replace(TOKEN, "<token>") if TOKEN else repr(e)[:200])
        ch = False
    return ch, ci_out.OUT[n0:]

if __name__ == "__main__":
    from ci_out import publish
    d = os.environ.get("NSE_DAY", "").strip()
    try:
        run_once(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=IST) if d else None)
    except Exception:
        import traceback
        p("ERROR", traceback.format_exc()[-900:])
    publish()
