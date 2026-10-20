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

def build(sym, name, link, st, final=False):
    """-> ('done', caption, png, key) / ('wait', reason) / ('skip', reason)"""
    s = nse.sess()
    rows = listing(s, sym)
    if not rows: return ("wait", "no XBRL listing yet")
    # newest quarter that has an XBRL filing; a quarter must exist on one basis for current, quarter-ago and year-ago
    for T in sorted({r["qe"] for r in rows}, reverse=True)[:2]:
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

def run_once(day=None, maxn=1):
    now = datetime.now(nse.IST)
    st = load(); changed = False
    if day or time.time() - _S["scan_at"] > 240:
        days = [day] if day else [now] + ([now - timedelta(days=1)] if now.hour < 3 else [])
        rows = []
        for d in days: rows += nse.result_rows(nse.fetch_day(d))
        _S["rows"] = [x for x in rows if (x.get("symbol") or "").upper() in FINSYMS]; _S["scan_at"] = time.time()
        p(f"bank/insurer result filings in window: {len(_S['rows'])}")
    n = 0
    for x in _S["rows"]:
        sym = x["symbol"].upper(); sid = str(x.get("seq_id"))
        if sid in st["done"]: continue
        if TRY.get(sid, (0, 0))[0] >= 40 or time.time() - TRY.get(sid, (0, 0))[1] < 120: continue
        TRY[sid] = (TRY.get(sid, (0, 0))[0] + 1, time.time())
        name = (x.get("sm_name") or sym).strip()
        out = build(sym, name, x.get("attchmntFile") or "", st)
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
    if not (LIVE and SEND and nse.CHAT) or time.time() - _S["last_tick"] < 60: return False, []
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
