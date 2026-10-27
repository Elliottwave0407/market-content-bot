import os, sys, json, re, time
from datetime import datetime, timedelta
import requests
from contextlib import nullcontext
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
import card
import pdf_card
import xbuttons
import tags

SEND = os.environ.get("POLL_SEND", "0") == "1"
MAX_POSTS = int(os.environ.get("POLL_MAX", "30"))
DAYS_BACK = int(os.environ.get("POLL_DAYS", "1"))
MIN_CR = float(os.environ.get("POLL_MIN_CR", "0"))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WAIT_H = float(os.environ.get("POLL_WAIT_HOURS", "0.75"))   # how long to wait for BSE numbers before posting a no-numbers card
ONLY = [x.strip().upper() for x in os.environ.get("POLL_ONLY", "").split(",") if x.strip()]   # test mode: only these companies, ignores/does not touch saved state
RETRY_SEC = int(os.environ.get("POLL_RETRY_SEC", "90"))
STATE = "state/seen.json"
_ST = None
PDF_AUDIT = {}
OUTDIR = "drafts/poll"
DISC = "For educational purpose only. Not an investment advice."

def redact(s):
    return str(s).replace(TOKEN, "<token>") if TOKEN else str(s)

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"ids": [], "posted": []}

_TEST_SEEN = set()

import threading
STATE_LOCK = threading.Lock()      # seen.json is written by this route and by the NSE-first route (other thread)

def disk_posted():
    try:
        return set(json.load(open(STATE)).get("posted", []))
    except Exception:
        return set()

def save_state(st):
    if ONLY:
        return
    os.makedirs("state", exist_ok=True)
    with STATE_LOCK:
        _save_state(st)

def _save_state(st):
    try:      # keep what the other route wrote meanwhile
        d_ = json.load(open(STATE))
        have = set(st["posted"])
        st["posted"] += [k_ for k_ in d_.get("posted", []) if k_ not in have]
    except Exception:
        pass
    st["ids"] = st["ids"][-5000:]
    st["posted"] = st["posted"][-5000:]
    json.dump(st, open(STATE, "w"), indent=0)

def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", timeout=60, **kw)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"non-json {r.status_code}"}

def mirror_to_channel(png, cap_clean, flink, key):
    """Second audience: copy every FULL result card (never a stub or a one-line digest) to the public channel in TELEGRAM_PUBLIC_GROUP_ID.
    Only a 'Filing' link button (anyone may tap it); no Post-to-X / Posted / Skip buttons. Does nothing when the secret is not set; never raises."""
    ch = os.environ.get("TELEGRAM_PUBLIC_GROUP_ID", "").strip()
    if not ch or not png or key.split("|")[-1] not in ("consolidated", "standalone"):
        return None
    try:
        d = {"chat_id": ch, "caption": cap_clean[:1024]}
        if flink:
            d["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "\U0001F4C4 Filing", "url": flink}]]})
        with open(png, "rb") as fh:
            r = tg("sendPhoto", data=d, files={"photo": fh})
        p(f"  channel copy ok={r.get('ok')} {redact(r.get('description', ''))}")
        return r
    except Exception as e:
        p("  channel copy failed:", type(e).__name__)
        return None

def fy_label(qlabel):
    d = datetime.strptime(qlabel, "%b-%y")
    qn = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    fy = d.year + 1 if d.month > 3 else d.year
    return f"Q{qn} FY{str(fy)[2:]}" if qn else qlabel

def link(rec):
    a = rec.get("ATTACHMENTNAME")
    return f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{a}" if a else rec.get("NSURL", "")

EARLY_OK = re.compile(r"outcome|financial results|results for|unaudited|audited", re.I)
EARLY_NO = re.compile(r"intimation|prior intimation|notice of|trading window|schedule of|postponement|clarification|newspaper|earnings call|conference call|investor meet|analyst", re.I)
EARLY_MAX_MIN = int(os.environ.get("EARLY_MAX_MIN", "30"))

def early_row(r):
    """The first filing that carries the numbers is often a 'Board Meeting' outcome row (minutes before the 'Result' row appears). Fresh ones only."""
    try:
        if r.get("CATEGORYNAME") != "Board Meeting" or not r.get("ATTACHMENTNAME"):
            return False
        t = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
        if not EARLY_OK.search(t) or EARLY_NO.search(t):
            return False
        from datetime import timezone
        now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)      # the runner clock is UTC, BSE stamps are IST
        age = (now_ist - datetime.fromisoformat((r.get("NEWS_DT") or "")[:19])).total_seconds() / 60
        return -2 <= age <= EARLY_MAX_MIN
    except Exception:
        return False

def fetch_filings(bse, known=None, fast=False):
    """Result filings. known: set of every NEWSID seen so far (updated here).
    fast=True: only the newest page(s) of today, stopping once an already-seen item appears."""
    prior = set(known) if known is not None else set()
    days = [0] if fast else list(range(DAYS_BACK, -1, -1))
    rows = []
    for back in days:
        d = datetime.now() - timedelta(days=back)
        pg, total_seen = 1, 0
        while pg <= 40:
            data = bse.announcements(page_no=pg, from_date=d, to_date=d)
            t = data.get("Table", [])
            if not t:
                break
            total_seen += len(t)
            for r_ in t:
                if r_.get("CATEGORYNAME") == "Result":
                    rows.append(r_)
                elif early_row(r_):
                    r_["_EARLY"] = True
                    rows.append(r_)
            if known is not None:
                known.update(r["NEWSID"] for r in t)
            if fast and any(r["NEWSID"] in prior for r in t):
                break
            if total_seen >= data.get("Table1", [{}])[0].get("ROWCNT", 0):
                break
            pg += 1
    seen, out = set(), []
    for r in rows:
        if r["NEWSID"] not in seen:
            seen.add(r["NEWSID"]); out.append(r)
    out.sort(key=lambda r: r.get("NEWS_DT") or "")
    return out

def stub(name, code, qlabel_, reason, lk, key):
    os.makedirs(OUTDIR, exist_ok=True)
    png = os.path.join(OUTDIR, f"stub_{code}_{qlabel_ or 'unknown'}.png")
    card.render_stub(name, f"BSE {code}", fy_label(qlabel_) if qlabel_ else "Result", reason, png)
    cap = f"{name} {fy_label(qlabel_) if qlabel_ else ''} results filed. Numbers not shown ({reason}).\nFiling: {lk}\n\n{DISC}"
    return ("photo", cap, png, key)

def inferred_qend(filed):
    """Quarter end implied by the filing date, used only when the headline names no quarter."""
    m, y = filed.month, filed.year
    if m in (10, 11, 12): return f"30.09.{y}"
    if m in (1, 2, 3): return f"31.12.{y - 1}"
    if m in (4, 5, 6): return f"31.03.{y}"
    return f"30.06.{y}"

_MC = {}
def size_ok(code, sales_cr):
    """Sanity: a company's quarterly sales cannot be absurdly small next to its market cap (a wrong unit or wrong table, e.g. Westlife read as Rs 0.3 Cr). True = fine or unknown."""
    try:
        if not _MC:
            _MC.update(json.load(open("state/mcap_cache.json")))
        m = _MC.get(str(code))
        if m and m[0] >= 500 and sales_cr is not None and sales_cr > 0 and sales_cr / m[0] < 1e-4:
            return False
    except Exception:
        pass
    return True

def build(bse, rec, final=False, age_min=0):
    """Return (kind, text, png_path or None, key). kind 'wait' = BSE numbers not there yet, retry later."""
    code, name = str(rec["SCRIP_CD"]), rec["SLONGNAME"]
    headline = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
    filed = datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19])
    lk = link(rec)
    pc = pdf_card.try_pdf(bse, rec, _ST, headline, filed) if _ST is not None else None
    if pc is None and rec.get("_EARLY"):
        return ("early_skip", "", None, "")      # an early 'Board Meeting' row is used only when its PDF reads cleanly; otherwise the 'Result' row follows
    if pc:
        basis, q, quarters = pc["basis"], pc["qcode"], pc["quarters"]
        ql = rf.qlabel(q)
        cur, prev, yago = quarters[0]["m"], quarters[1]["m"], quarters[4]["m"]
        sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
        if not size_ok(code, sales):
            return stub(name, code, ql, "figures look inconsistent with the company's size - please verify against the filing", lk, f"{code}|{ql}|anomaly")
        sd = 0 if sales and sales >= 100 else 1
        pd_ = 0 if pat and pat >= 100 else 1
        sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
        png = os.path.join(OUTDIR, f"{code}_{ql}_{basis}.png")
        k5 = (str(code), basis, q - 5)
        if k5 in pdf_card.HIST:
            yprev = pdf_card.HIST.pop(k5)
        else:
            try: yprev = rf.fetch(bse, code, name, basis, q - 5)
            except Exception: yprev = None
        card.render(name, f"BSE {code}", basis, quarters, png, yprev=yprev)
        cap = (f"{name} {fy_label(ql)} | {basis.capitalize()}\n"
               f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
               f"{'(Quarter taken from the PDF.) ' if pc['inferred'] else ''}Filing: {lk}\n\n{DISC}")
        key = f"{code}|{ql}|{basis}"
        PDF_AUDIT[key] = {"code": code, "name": name, "basis": basis, "q": q, "rev": cur["revenue"], "pat": cur["pat"], "t": time.time(), "last": 0}
        return ("photo", cap, png, key)
    res = rf.results_for_filing(bse, code, name, headline, filed)
    inferred = False
    if res["status"] == "quarter_unverified":
        headline = headline + " quarter ended " + inferred_qend(filed)
        res = rf.results_for_filing(bse, code, name, headline, filed)
        inferred = True
    st = res["status"]
    if st == "quarter_unverified":
        return stub(name, code, None, "quarter not identified from the filing headline", lk, f"{code}|unverified|{rec['NEWSID']}")
    if st in ("not_available", "ok_limited"):
        if not final:
            return ("wait", "numbers not yet on BSE", None, f"{code}|{res['quarter']}|wait")
        reason = "BSE has not published structured numbers for this filing" if st == "not_available" else "only limited data available from BSE for this format"
        return stub(name, code, res["quarter"], reason, lk, f"{code}|{res['quarter']}|na")
    basis = "consolidated" if res["consolidated"] else "standalone"
    cons_expected = bool((_ST or {}).get("cons_expected", {}).get(str(rec["NEWSID"]))) or "consolidated" in headline.lower()
    cons_missing = False
    if basis == "standalone":
        # STANDING RULE: never post standalone while a consolidated result exists or may exist.
        so = bool((_ST or {}).get("standalone_only", {}).get(str(rec["NEWSID"])))
        if cons_expected:
            if age_min < 180:
                return ("wait", "consolidated numbers not yet on BSE", None, f"{code}|{res['quarter']}|wait")
            return stub(name, code, res["quarter"], "consolidated numbers not yet published on BSE", lk, f"{code}|{res['quarter']}|nocons")
        if not so and age_min < 120:
            return ("wait", "confirming that no consolidated statement exists", None, f"{code}|{res['quarter']}|wait")
    q = rf.expected_quarter(headline, filed)
    quarters = [{"q": rf.qlabel(q - i), "m": rf.fetch(bse, code, name, basis, q - i)} for i in range(5)]
    try: yprev = rf.fetch(bse, code, name, basis, q - 5)      # quarter before the year-ago one: only used by the rating's seasonality adjustment
    except Exception: yprev = None
    if not quarters[0]["m"]:
        if not final:
            return ("wait", "comparison data incomplete", None, f"{code}|{res['quarter']}|wait")
        return stub(name, code, res["quarter"], "comparison data incomplete", lk, f"{code}|{res['quarter']}|incomplete")
    for qq in quarters:
        if qq["m"] is None:
            qq["m"] = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
    cur, prev, yago = quarters[0]["m"], quarters[1]["m"], quarters[4]["m"]
    # STANDING RULE: a result card carries all 5 rows (sales, operating profit, OPM, net profit, EPS) - banks/NBFCs have no operating-profit row.
    need = ("revenue", "pat", "eps") + (() if cur.get("bank") else ("ebitda",))
    miss = sorted({k_ for qq in (quarters[0], quarters[1], quarters[4]) for k_ in need if qq["m"].get(k_) is None})
    incomplete = bool(miss)
    if incomplete and not final and ((cur.get("revenue") or 0) / 10.0) >= MIN_CR:   # smaller companies only appear as one digest line (sales + profit), no card
        return ("wait", f"incomplete metrics {miss}; retrying the PDF read", None, f"{code}|{res['quarter']}|wait")
    r0, r1 = cur.get("revenue"), prev.get("revenue")
    if r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50):
        return stub(name, code, res["quarter"], "figures look inconsistent with the previous quarter - please verify", lk, f"{code}|{res['quarter']}|anomaly")
    sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
    if not size_ok(code, sales):
        return stub(name, code, res["quarter"], "figures look inconsistent with the company's size - please verify against the filing", lk, f"{code}|{res['quarter']}|anomaly")
    sd = 0 if sales and sales >= 100 else 1
    pd_ = 0 if pat and pat >= 100 else 1
    sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
    if sales is None or sales < MIN_CR:
        return ("line", f"{name} {fy_label(res['quarter'])} {"cons" if basis=="consolidated" else "stand"}: Sales {card.fmt_num(sales, sd)} Cr ({sy} YoY), PAT {card.fmt_num(pat, pd_)} Cr ({py} YoY) | {lk}", None, f"{code}|{res['quarter']}|{basis}")
    png = os.path.join(OUTDIR, f"{code}_{res['quarter']}_{basis}.png")
    card.render(name, f"BSE {code}", basis, quarters, png, yprev=yprev)
    cap = (f"{name} {fy_label(res['quarter'])} | {basis.capitalize()}\n"
           f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
           f"{'(Quarter inferred from filing date.) ' if inferred else ''}{('(Not available from BSE after 24 h: ' + ', '.join(miss) + '.) ') if incomplete else ''}Filing: {lk}\n\n{DISC}")
    return ("photo", cap, png, f"{code}|{res['quarter']}|{basis}")

def audit(bse, st, chat):
    """Compare PDF-based cards with BSE's table once it appears; warn the group on a real difference."""
    now = time.time()
    done = 0
    for key, info in list(st.get("pdfposted", {}).items()):
        if now - info["t"] > 48 * 3600:
            st["pdfposted"].pop(key, None); continue
        if now - info.get("last", 0) < 300 or done >= 4:
            continue
        info["last"] = now
        done += 1
        try:
            m = rf.fetch(bse, info["code"], info["name"], info["basis"], info["q"])
        except Exception:
            continue
        if not m or m.get("revenue") is None:
            continue
        rev_ok = abs(info["rev"] - m["revenue"]) <= max(0.6, 0.005 * abs(m["revenue"]))
        pat_ok = m.get("pat") is None or abs(info["pat"] - m["pat"]) <= max(1.0, 0.03 * abs(m["pat"]))
        st.setdefault("audit", []).append([info["name"], "ok" if rev_ok and pat_ok else "diff"])
        st["audit"] = st["audit"][-300:]
        p(f"[audit] {info['name']}: {'match' if rev_ok and pat_ok else 'DIFF'}")
        if not (rev_ok and pat_ok) and SEND:
            c = lambda v: f"{v / 10:,.1f}"
            tg("sendMessage", json={"chat_id": chat, "text": f"Check needed: {info['name']} card was read from the filing PDF (Sales {c(info['rev'])} Cr, PAT {c(info['pat'])} Cr) but BSE's table now shows Sales {c(m['revenue'])} Cr, PAT {c(m.get('pat') or 0)} Cr. Please verify against the filing."})
        st["pdfposted"].pop(key, None)

def main(bse_in=None, known=None, fast=False):
    global _ST
    os.makedirs(OUTDIR, exist_ok=True)
    st = load_state()
    _ST = st
    pdf_card.new_poll()
    PDF_AUDIT.clear()
    chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    posted = 0
    ctx = nullcontext(bse_in) if bse_in is not None else BSE(download_folder="./")
    with ctx as bse:
        filings = fetch_filings(bse, known, fast)
        if ONLY:
            new = [r for r in filings if any(k in (r.get("SLONGNAME") or "").upper() for k in ONLY)]
        else:
            new = [r for r in filings if r["NEWSID"] not in st["ids"]]
        p(f"mode={'SEND' if SEND else 'DRY-RUN'} filings={len(filings)} new={len(new)} cap={MAX_POSTS}")
        lines = []
        now = time.time()
        pend = st.setdefault("pending", {})
        new_ids = {r["NEWSID"] for r in new}
        retry = [v["rec"] for k, v in list(pend.items()) if k not in new_ids and now - v["last"] >= RETRY_SEC]
        try:      # read several filings' PDFs at the same time (a burst of results no longer queues one by one)
            def _skip_fin(r_):
                import fin_results as _fr
                return _fr.is_fin_code(r_.get("SCRIP_CD")) and (datetime.now() - datetime.fromisoformat((r_.get("NEWS_DT") or "")[:19])).total_seconds() / 3600 < _fr.YIELD_H
            _batch = []
            for r_ in sorted(new + retry, key=lambda x_: -pdf_card.mcap_of(x_.get("SCRIP_CD"))):
                try:
                    if not _skip_fin(r_): _batch.append(r_)
                except Exception:
                    _batch.append(r_)
            pdf_card.prefetch(_batch[:12], st)
        except Exception as e:
            p(f"prefetch skipped: {redact(repr(e))[:100]}")
        for rec in sorted(new + retry, key=lambda x_: -pdf_card.mcap_of(x_.get("SCRIP_CD"))):      # biggest companies first
            nid = rec["NEWSID"]
            try:      # banks/insurers: the NSE XBRL route (fin_results) posts them; this route only steps in after YIELD_H hours
                import fin_results as _fr
                if _fr.is_fin_code(rec.get("SCRIP_CD")):
                    _age = (datetime.now() - datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19])).total_seconds() / 3600
                    if _age < _fr.YIELD_H:
                        continue
            except Exception:
                pass
            first = pend.get(nid, {}).get("first", now)
            try:
                out = build(bse, rec, final=(now - first) > WAIT_H * 3600, age_min=(10**6 if ONLY else (now - first) / 60))
            except Exception as e:
                p(f"ERROR {rec.get('SLONGNAME')}: {redact(repr(e))[:200]}")
                continue
            kind, text, png, key = out
            if kind == "early_skip":
                if nid in pdf_card.EARLY_DEAD or pdf_card.TRIES.get(nid, 0) >= 8:
                    st["ids"].append(nid)
                continue
            if kind == "wait":
                if nid not in pend:
                    p(f"[wait] {rec.get('SLONGNAME')} ({key}) - BSE numbers not published yet, will retry")
                pend[nid] = {"rec": rec, "first": first, "last": now}
                continue
            if kind != "line" and posted >= MAX_POSTS:
                continue
            if ONLY:
                if key in _TEST_SEEN:
                    continue
                _TEST_SEEN.add(key)
            if (key in st["posted"] or key in disk_posted()) and not ONLY:
                p(f"dup skip {key}")
                st["ids"].append(rec["NEWSID"])
                pend.pop(nid, None)
                continue
            p(f"[{kind}] {key} :: {text[:160]!r}")
            if kind == "line":
                lines.append((rec["NEWSID"], key, text))
                continue
            if SEND:
                if kind == "photo":
                    cap_clean, flink = xbuttons.split_link(text)
                    nm = (rec.get("SLONGNAME") or "").strip()
                    parts = key.split("|")
                    ql = parts[1] if len(parts) > 1 else ""
                    tweet = "\n".join(text.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(code=rec.get("SCRIP_CD"), name=nm), tags.quarter_tag(ql), "#Results")
                    r = tg("sendPhoto", data={"chat_id": chat, "caption": cap_clean[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": open(png, "rb")})
                else:
                    r = tg("sendMessage", json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
                p(f"  sent ok={r.get('ok')} {redact(r.get('description', ''))}")
                if not r.get("ok"):
                    continue
                if kind == "photo":
                    mirror_to_channel(png, cap_clean, flink, key)
                try:
                    import store
                    if kind == "photo": store.log_result("bse", text, r, card.LAST, rec.get("NEWS_DT"))
                    else: store.log_post("bse-text", text, r)
                except Exception:
                    pass
                time.sleep(3.2)
            if ONLY:
                posted += 1
                continue
            st["ids"].append(rec["NEWSID"])
            st["posted"].append(key)
            if key in PDF_AUDIT and SEND:
                st.setdefault("pdfposted", {})[key] = PDF_AUDIT[key]
            if nid in pend:
                st.setdefault("lag", []).append([rec.get("SLONGNAME"), round((now - pend[nid]["first"]) / 60)])
                st["lag"] = st["lag"][-300:]
                p(f"  resolved after {round((now - pend[nid]['first']) / 60)} min wait")
                pend.pop(nid, None)
            posted += 1
            if SEND:
                save_state(st)
        # one digest message for smaller companies
        lines = lines[:40]
        if lines:
            body = f"Smaller results (sales below Rs {MIN_CR:.0f} Cr), consolidated if available, else standalone. Filed numbers; verify with filing.\n\n" + "\n".join(l[2] for l in lines)
            p(f"[digest] {len(lines)} lines")
            ok = True
            if SEND:
                r = tg("sendMessage", json={"chat_id": chat, "text": body[:4000], "disable_web_page_preview": True})
                ok = r.get("ok")
                p(f"  digest sent ok={ok} {redact(r.get('description', ''))}")
            if ok:
                for nid, key, _ in lines:
                    st["ids"].append(nid); st["posted"].append(key)
        if SEND:
            try:
                audit(bse, st, chat)
            except Exception as e:
                p(f"audit error {redact(repr(e))[:120]}")
    if SEND:
        save_state(st)
    for x in pdf_card.LOG:
        p("[pdf]", x)
    pdf_card.LOG.clear()
    p(f"done: {posted} {'sent' if SEND else 'would send'}")
    return posted

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        p("Caught error:", redact(repr(e))[:300])
    publish()
    sys.exit(0)
