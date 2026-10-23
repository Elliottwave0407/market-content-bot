"""Fast path: read the filing PDF with Gemini, verify it, return card data. Returns None whenever anything is doubtful."""
import os, re, time
from datetime import datetime, timedelta
import requests
import results_fetcher as rf
import gemini_read as gr

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-flash-lite-latest"
DAILY_CAP = int(os.environ.get("GEMINI_DAILY_CAP", "450"))
PER_POLL = int(os.environ.get("PDF_PER_POLL", "10"))
K = {"lakh": 0.1, "lakhs": 0.1, "lac": 0.1, "lacs": 0.1, "crore": 10.0, "crores": 10.0, "million": 1.0, "thousand": 0.001, "actual": 1e-6}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
TRIES, STATE_, LAST_TRY = {}, {"backoff": 0.0, "calls": 0}, {}
LOG = []

def new_poll():
    STATE_["calls"] = 0

def parse_qend(s):
    s = str(s or "").lower()
    m = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})", s)
    if m:
        mo, y = int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s.,'-]*(\d{1,2})?[\s.,'-]*(\d{4}|\d{2})\b", s)
        if not m:
            return None
        mo, y = MONTHS[m.group(1)], int(m.group(3))
    if y < 100:
        y += 2000
    return (y, mo) if mo in (3, 6, 9, 12) else None

def val(d, key, i):
    v = (d or {}).get(key)
    return v[i] if isinstance(v, list) and len(v) > i and isinstance(v[i], (int, float)) else None

def arith_ok(d):
    ti, ex, pbt, tax, pat = (val(d, x, 0) for x in ("total_income", "total_expenses", "pbt", "tax", "pat"))
    tol = lambda a, b: abs(a - b) <= max(1.5, 0.002 * max(abs(a), abs(b)))
    res = []
    if None not in (ti, ex, pbt):
        dp0, fn0 = val(d, "depreciation", 0), val(d, "finance_costs", 0)
        # layout A: total expenses include depreciation and finance costs; layout B (e.g. Sterlite): they are listed below it
        res.append(tol(ti - ex, pbt) or (None not in (dp0, fn0) and tol(ti - ex - dp0 - fn0, pbt)))
    if None not in (pbt, tax, pat):
        res.append(tol(pbt - tax, pat))
    return bool(res) and all(res), len(res)

def to_m(d, i, k):
    rev, pbt, pat, eps = (val(d, x, i) for x in ("revenue", "pbt", "pat", "eps"))
    exp, dep, fin = (val(d, x, i) for x in ("total_expenses", "depreciation", "finance_costs"))
    ebitda = None
    if None not in (rev, exp, dep, fin) and rev and fin / rev < 0.25:
        ti_ = val(d, "total_income", i)
        tl_ = lambda a, b: abs(a - b) <= max(1.5, 0.002 * max(abs(a), abs(b)))
        layout_b = ti_ is not None and pbt is not None and (not tl_(ti_ - exp, pbt)) and tl_(ti_ - exp - dep - fin, pbt)
        ebitda = (rev - exp if layout_b else rev - exp + dep + fin) * k    # layout B: "total expenses" already EXCLUDES depreciation and finance costs
        if rev > 0 and not (-100 <= 100 * ebitda / (rev * k) <= 100):      # a margin outside +-100% means a mis-read line: show no margin rather than a wrong one
            ebitda = None
    sc = lambda v: None if v is None else v * k
    return {"revenue": sc(rev), "ebitda": ebitda, "pbt": sc(pbt), "pat": sc(pat), "eps": eps, "bank": False, "fin": sc(fin)}

def close(a, b):
    return abs(a - b) <= max(0.6, 0.005 * abs(b))

def geminikey():
    return os.environ.get("GEMINI_API_KEY", "").strip()

KEYS = ("revenue from operations", "total income", "profit before tax", "profit/(loss) before tax", "profit / (loss) before tax", "total expenses")

def trim_pdf(content):
    """Keep only the pages that carry the results table (plus the page after the first one, for tables that run over), so Gemini reads a page or two, not a 40-page filing.
    Scanned/odd files (no text layer, no table found) come back unchanged."""
    if os.environ.get("PDF_TRIM", "1") != "1":
        return content
    try:
        import fitz
        d = fitz.open(stream=content, filetype="pdf")
        if d.page_count <= 3:
            return content
        hits = []
        for i in range(d.page_count):
            t = d[i].get_text().lower()
            if sum(k in t for k in KEYS) >= 2:
                hits.append(i)
        if not hits:
            return content
        keep = sorted(set(hits[:4]) | {min(hits[0] + 1, d.page_count - 1)})
        if len(keep) >= d.page_count:
            return content
        out = fitz.open()
        for i in keep:
            out.insert_pdf(d, from_page=i, to_page=i)
        return out.tobytes()
    except Exception:
        return content

RULE_BAD = set()      # filings whose rule-read numbers failed a later check: read by Gemini / NVIDIA instead
EARLY_DEAD = set()      # early 'Board Meeting' rows whose PDF has no results table (nothing to read)
PREREAD = {}      # nid -> result of the download+Gemini stage, prepared in parallel threads by prefetch()

def has_results_table(content):
    """Free local check (no Gemini): does any page carry a results statement? Scanned files without a text layer say no."""
    try:
        import fitz
        d = fitz.open(stream=content, filetype="pdf")
        for i in range(d.page_count):
            t = d[i].get_text().lower()
            if sum(k in t for k in KEYS) >= 2:
                return True
    except Exception:
        return True
    return False

def _annotate(out, small):
    """Mark whether the current column's headline numbers are printed in the PDF's own text layer (guards against a misread; scanned PDFs have no text and stay unmarked)."""
    try:
        import nim_read as nr
        txt = nr.pdf_text(small, limit=250000)
        if len(re.sub(r"\W", "", txt)) > 400:
            out["_printed"] = {b: nr.cur_unsupported(out, txt, b) for b in ("consolidated", "standalone")}
    except Exception:
        pass
    return out

def _read_stage(rec, st, headline, filed):
    """Download the filing PDF and read it with Gemini. -> (out, q_head) or None (gated / failed). Thread-safe enough: only dict and counter updates."""
    key = geminikey()
    att = rec.get("ATTACHMENTNAME")
    nid = rec["NEWSID"]
    if not att or os.environ.get("PDF_FAST", "1") != "1":
        return None
    import nim_read as nr
    nim_ok = bool(nr.key())
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))
    use = st.setdefault("gem_use", {})
    gem_blocked = (not key) or time.time() < STATE_["backoff"] or use.get(day, 0) >= DAILY_CAP or os.environ.get("NIM_ONLY") == "1"
    if TRIES.get(nid, 0) >= 8 or time.time() - LAST_TRY.get(nid, 0) < (30 if rec.get("_EARLY") else 240):
        return None
    q_head = rf.expected_quarter(headline, filed)
    TRIES[nid] = TRIES.get(nid, 0) + 1
    LAST_TRY[nid] = time.time()
    content = b""
    for folder in ("AttachLive", "AttachHis"):
        try:
            r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{att}", headers=UA, timeout=45)
        except Exception:
            continue
        if r.content[:4] == b"%PDF":
            content = r.content
            break
    if not content or len(content) > 15_000_000:
        return None
    if rec.get("_EARLY") and not has_results_table(content):
        EARLY_DEAD.add(nid)
        return None
    small = trim_pdf(content)
    if os.environ.get("RULE_READ", "1") == "1" and os.environ.get("NIM_ONLY") != "1" and nid not in RULE_BAD:
        try:    # rule reader first: the numbers come straight from the PDF text, no AI call, no quota; only a statement that reconciles in all three columns is accepted
            import rule_read as rr
            r_out, r_err = rr.read_pdf(small, hint=headline, qhint=q_head)
            if r_out is None and small is not content:
                r_out, r_err = rr.read_pdf(content, hint=headline, qhint=q_head)
            LOG.append(f"rule reader {rec.get('SLONGNAME')}: {'ok' if r_out else r_err}")
            if r_out is not None:
                return r_out, q_head
        except Exception as e_:
            LOG.append(f"rule reader error {rec.get('SLONGNAME')}: {repr(e_)[:80]}")
    if (gem_blocked and not nim_ok) or STATE_["calls"] >= PER_POLL:
        TRIES[nid] = max(0, TRIES.get(nid, 1) - 1)
        return None
    STATE_["calls"] += 1
    out, err = None, "gemini skipped (quota/backoff)"
    if not gem_blocked:
        use[day] = use.get(day, 0) + 1
        out, err = gr.read_pdf(key, MODEL, small, tries=int(os.environ.get("PDF_TRIES", "1")), timeout=90)
        if out is None and small is not content and not (err and "429" in err):
            out, err = gr.read_pdf(key, MODEL, content, tries=int(os.environ.get("PDF_TRIES", "1")), timeout=90)     # trimmed read failed: try the whole file
    if out is None and nim_ok:      # Gemini out of quota / busy / failed: the free NVIDIA reader takes the same job (same checks follow)
        out, err2 = nr.read_pdf(small)
        LOG.append(f"nim reader {rec.get('SLONGNAME')}: {'ok' if out else err2} (gemini: {str(err)[:40]})")
        if out is not None:
            return _annotate(out, small), q_head
        err = f"{err}; {err2}"
    if out is None:
        if err and ("429" in err or "503" in err):
            STATE_["backoff"] = time.time() + 120
            TRIES[nid] = max(0, TRIES.get(nid, 1) - 1)    # a quota / busy answer is not the filing's fault: do not use up its tries (23 Oct: 20+ filings gave up during a quota outage)
        LOG.append(f"pdf read failed {rec.get('SLONGNAME')}: {str(err)[:80]}")
        return None
    return _annotate(out, small), q_head

def prefetch(recs, st, workers=4):
    """Run the download+Gemini stage for several filings at the same time (it is network wait, not CPU), so a burst of results does not queue up one by one."""
    todo = []
    for rec in recs:
        nid = rec.get("NEWSID")
        if nid is None or nid in PREREAD or not rec.get("ATTACHMENTNAME"): continue
        todo.append(rec)
    if len(todo) < 2: return
    from concurrent.futures import ThreadPoolExecutor
    def one(rec):
        try:
            headline = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
            filed = datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19])
            PREREAD[rec["NEWSID"]] = _read_stage(rec, st, headline, filed)
        except Exception as e:
            LOG.append(f"prefetch error: {repr(e)[:80]}")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))

HIST = {}      # (code, basis, quarter) -> history fetched ahead for the card's year-ago-previous cell

def hist_batch(bse, code, name, basis, qs):
    """Fetch BSE's filed history for several quarters at the same time (was one after another). A failed fetch re-raises when that quarter is asked for, as before."""
    from concurrent.futures import ThreadPoolExecutor
    def one(qq):
        for t in range(2):
            try:
                return rf.fetch(bse, code, name, basis, qq)
            except Exception as e:
                err = e
                time.sleep(0.5)
        return err
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, qs))
    for qq, v in zip(qs, res):
        if not isinstance(v, Exception) and qq == qs[-1]:
            HIST[(str(code), basis, qq)] = v
    def get(qq):
        v = res[qs.index(qq)]
        if isinstance(v, Exception):
            raise v
        return v
    return get

def try_pdf(bse, rec, st, headline, filed):
    """-> dict(basis, qcode, quarters, verified_note, raw) or None."""
    nid = rec["NEWSID"]
    res_ = PREREAD.pop(nid) if nid in PREREAD else _read_stage(rec, st, headline, filed)
    if res_ is None:
        return None
    r = _try_pdf(bse, rec, st, headline, filed, res_)
    if r is None and res_[0].get("_rule") and not res_[0].get("_keep"):
        RULE_BAD.add(nid)       # the rule-read numbers did not survive the later checks (history, columns): let the AI reader look at this filing
        TRIES[nid] = max(0, TRIES.get(nid, 1) - 1)
        LAST_TRY.pop(nid, None)
        LOG.append(f"rule-read numbers rejected by later checks, AI reader will retry: {rec.get('SLONGNAME')}")
    return r

def _try_pdf(bse, rec, st, headline, filed, res_):
    nid = rec["NEWSID"]
    out, q_head = res_
    try:   # remember that this filing HAS consolidated figures, so the BSE-table fallback never posts standalone for it
        c_ = out.get("consolidated")
        if isinstance(c_, dict) and val(c_, "revenue", 0) is not None and val(c_, "pat", 0) is not None:
            ce = st.setdefault("cons_expected", {})
            ce[str(nid)] = 1
            if len(ce) > 600:
                for k_ in list(ce)[:100]:
                    ce.pop(k_, None)
        s_ = out.get("standalone")
        if not (isinstance(c_, dict) and val(c_, "pat", 0) is not None) and isinstance(s_, dict) and val(s_, "revenue", 0) is not None and val(s_, "pat", 0) is not None:
            so_ = st.setdefault("standalone_only", {})   # the PDF itself shows no consolidated statement: standalone is the real basis
            so_[str(nid)] = 1
            if len(so_) > 600:
                for k_ in list(so_)[:100]:
                    so_.pop(k_, None)
    except Exception:
        pass
    k = K.get(str(out.get("unit", "")).lower())
    cols = out.get("quarter_end_columns") or []
    qe = parse_qend(cols[0]) if cols else None
    if not k or qe is None:
        LOG.append(f"pdf unusable {rec.get('SLONGNAME')}: unit/date missing")
        return None
    # Column dates must form a QUARTERLY layout: previous = 3 months earlier and year-ago = 12 months earlier (in either order).
    # A half-yearly filing (SME: current | year-ago half | previous half, or current | previous half | year-ago half) must never be read as quarters.
    try:
        ms0 = []
        for c in cols[:3]:
            pq0 = parse_qend(c)
            ms0.append(pq0[0] * 12 + pq0[1] if pq0 else None)
        if len(ms0) == 3 and None not in ms0:
            d1_, d2_ = ms0[0] - ms0[1], ms0[0] - ms0[2]
            if (d1_, d2_) in ((6, 12), (12, 6)):
                hq = st.setdefault("half_q", {})
                hq[str(nid)] = {k_: rec.get(k_) for k_ in ("NEWSID", "SCRIP_CD", "SLONGNAME", "ATTACHMENTNAME", "NEWS_DT")}
                for k_ in list(hq)[:-200]:
                    hq.pop(k_, None)
                TRIES[nid] = 99      # stop retrying this filing as quarters
                LOG.append(f"pdf is a HALF-YEARLY filing (column dates {cols[:3]}): not read as quarters, queued for the half-yearly route {rec.get('SLONGNAME')}")
                return None
            if (d1_, d2_) not in ((3, 12), (12, 3)):
                LOG.append(f"pdf column dates {cols[:3]} are not a quarterly layout: not used {rec.get('SLONGNAME')}")
                return None
    except Exception as e_:
        LOG.append(f"pdf column-date check failed: {repr(e_)[:60]}")
    # Some filings list the columns as current | year-ago | previous. If the model reported the column dates in that order, swap the number columns to match.
    try:
        ms = []
        for c in cols[:3]:
            pq = parse_qend(c)
            ms.append(pq[0] * 12 + pq[1] if pq else None)
        if len(ms) == 3 and None not in ms and (ms[0] - ms[1]) >= 9 and 1 <= (ms[0] - ms[2]) <= 5:
            for b_ in ("consolidated", "standalone"):
                d_ = out.get(b_)
                if isinstance(d_, dict):
                    for kk, vv in list(d_.items()):
                        if isinstance(vv, list) and len(vv) >= 3:
                            vv[1], vv[2] = vv[2], vv[1]
            LOG.append(f"pdf columns were current|year-ago|previous: swapped {rec.get('SLONGNAME')}")
    except Exception as e_:
        LOG.append(f"pdf column-order check failed: {repr(e_)[:60]}")
    q_pdf = rf.qcode(qe[0], qe[1])
    if q_head is not None and q_head != q_pdf:
        LOG.append(f"pdf quarter mismatch {rec.get('SLONGNAME')}")
        return None
    q = q_pdf
    for basis in ("consolidated", "standalone"):
        d = out.get(basis)
        if not d or val(d, "revenue", 0) is None or val(d, "pat", 0) is None:
            continue
        if basis == "standalone" and out.get("consolidated") and val(out["consolidated"], "pat", 0) is not None:
            LOG.append(f"pdf has consolidated but it failed checks: not falling back to standalone {rec.get('SLONGNAME')}")
            return None
        ok, n = arith_ok(d)
        ok = ok or bool((out.get("_rule_ok") or {}).get(basis))     # the rule reader already proved the statement reconciles in all three columns (incl. exceptional items / associates)
        LOG.append(f"pdf current col {rec.get('SLONGNAME')} {basis} ok={ok}/{n}: " + ", ".join(f"{x}={val(d, x, 0)}" for x in ("revenue", "other_income", "total_income", "total_expenses", "finance_costs", "depreciation", "pbt", "tax", "pat", "eps")))
        cur, prev, yago = (to_m(d, i, k) for i in range(3))
        code, name = str(rec["SCRIP_CD"]), rec["SLONGNAME"]
        fx = hist_batch(bse, code, name, basis, [q, q - 1, q - 2, q - 3, q - 4, q - 5])
        cur_bse = False   # BSE's own table for THIS quarter (if already published) independently confirms the PDF's current column
        try:
            h0 = fx(q)
            if h0 and h0.get("revenue") is not None and h0.get("pat") is not None and cur["revenue"] is not None and cur["pat"] is not None:
                cur_bse = close(cur["revenue"], h0["revenue"]) and abs(cur["pat"] - h0["pat"]) <= max(1.0, 0.03 * abs(h0["pat"]))
        except Exception:
            pass
        if cur_bse and not ok:
            LOG.append(f"pdf current column matches BSE's current table (revenue and profit): arithmetic gap ignored {name} {basis}")
        ok = ok or cur_bse
        hist, hpat, det, hs = {}, {}, [], {}
        for off, m in ((1, prev), (4, yago)):
            h = fx(q - off)
            hs[off] = h
            det.append(f"q-{off}: pdf rev {m.get('revenue')} pat {m.get('pat')} | bse rev {h and h.get('revenue')} pat {h and h.get('pat')} (Rs mn)")
            if h and h.get("revenue") is not None and m["revenue"] is not None:
                hist[off] = close(m["revenue"], h["revenue"])
            if h and h.get("pat") is not None and m["pat"] is not None:
                hpat[off] = abs(m["pat"] - h["pat"]) <= max(1.0, 0.03 * abs(h["pat"]))
        for off_, m_ in ((1, prev), (4, yago)):      # operating margin must agree with BSE's own filed history; if not, show NO margin (and no verdict) instead of a wrong one
            h_ = hs.get(off_)
            if h_ and hist.get(off_) and h_.get("ebitda") is not None and h_.get("revenue") and m_.get("ebitda") is not None and m_.get("revenue"):
                gap_ = abs(100 * m_["ebitda"] / m_["revenue"] - 100 * h_["ebitda"] / h_["revenue"])
                if gap_ > 3.0:
                    LOG.append(f"pdf margin q-{off_} differs from BSE history by {gap_:.1f} pts: margin withheld {name} {basis}")
                    m_["ebitda"] = None
        if hist and not all(hist.values()) and len(hist) == 2 and hs.get(1) and hs.get(4):
            # the filing may list year-ago before previous quarter: accept the swap only if BSE history matches the swapped columns on revenue AND profit
            a, b2 = hs[1], hs[4]
            if None not in (a.get("revenue"), a.get("pat"), b2.get("revenue"), b2.get("pat"), prev["revenue"], prev["pat"], yago["revenue"], yago["pat"]) \
                    and close(prev["revenue"], b2["revenue"]) and close(yago["revenue"], a["revenue"]) \
                    and abs(prev["pat"] - b2["pat"]) <= max(1.0, 0.03 * abs(b2["pat"])) and abs(yago["pat"] - a["pat"]) <= max(1.0, 0.03 * abs(a["pat"])):
                for kk, vv in list(d.items()):
                    if isinstance(vv, list) and len(vv) >= 3:
                        vv[1], vv[2] = vv[2], vv[1]
                cur, prev, yago = (to_m(d, i, k) for i in range(3))
                hist = {1: True, 4: True}
                hpat = {1: True, 4: True}
                LOG.append(f"pdf previous/year-ago columns were swapped vs BSE history: corrected {name} {basis}")
        if hist and not all(hist.values()) and ok:
            # The previous/year-ago cell of the PDF may carry a typo (digit slip): if PROFIT matches BSE's filed history for that column but
            # revenue does not, trust BSE's history for that column and keep the PDF's current quarter (its own arithmetic already checked).
            fixed = []
            for off, m_ in ((1, prev), (4, yago)):
                h_ = hs.get(off)
                if hist.get(off) is False and hpat.get(off) is True and h_ and h_.get("revenue") is not None:
                    LOG.append(f"pdf q-{off} revenue typo: pdf {m_['revenue']} -> BSE history {h_['revenue']} (profit matched) {name}")
                    m_["revenue"] = h_["revenue"]
                    ex_, dp_, fn_ = (val(d, x_, off) for x_ in ("total_expenses", "depreciation", "finance_costs"))
                    m_["ebitda"] = (h_["revenue"] / k - ex_ + dp_ + fn_) * k if None not in (ex_, dp_, fn_) else h_.get("ebitda")
                    hist[off] = True
                    fixed.append(off)
            if fixed:
                LOG.append(f"pdf history cells corrected from BSE for q-{fixed}: {name} {basis}")
        if hist and not all(hist.values()):
            LOG.append(f"pdf history mismatch {name} {basis} cols={cols[:3]} :: " + "; ".join(det))
            continue
        strong = len(hist) == 2 and len(hpat) == 2 and all(hpat.values())
        printed_ok = (out.get("_printed") or {}).get(basis) == 0
        pat_chain = None not in (val(d, "pbt", 0), val(d, "tax", 0), val(d, "pat", 0)) and abs(val(d, "pbt", 0) - val(d, "tax", 0) - val(d, "pat", 0)) <= max(1.5, 0.002 * abs(val(d, "pat", 0)))
        relaxed = (not ok and not strong and printed_ok and pat_chain)     # table arithmetic does not reconcile (associates, exceptional items...) but the headline numbers are printed in the filing and pbt - tax = pat
        if not ok and not strong and not relaxed:
            LOG.append(f"pdf checks failed {name} {basis}")
            continue
        if relaxed:
            LOG.append(f"pdf accepted on printed-numbers check (table arithmetic not reconciled) {name} {basis}")
        if ok:
            note = "history-verified" if hist else "no BSE history (arithmetic-checked only)"
        else:
            note = "verified against BSE's previous quarters"
        r0, r1 = cur["revenue"], prev["revenue"]
        if r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50):
            return None
        rv0, fc0 = val(d, "revenue", 0), val(d, "finance_costs", 0)
        fin_heavy = bool(rv0 and fc0 is not None and fc0 / rv0 >= 0.25)   # banks / NBFCs: no operating-profit row
        try:
            age_f = (datetime.utcnow() + timedelta(hours=5, minutes=30) - filed).total_seconds() / 60
        except Exception:
            age_f = 0
        # EPS may be missing from a filing's table (shown as '-'); operating profit may be unverifiable: give BSE's own table 10 minutes to supply it, then post the card without it rather than wait for a day
        need = ("revenue", "pat") + (() if fin_heavy or age_f >= 10 else ("ebitda",))
        miss = sorted({kk for m_ in (cur, prev, yago) for kk in need if m_.get(kk) is None})
        if miss:
            LOG.append(f"pdf incomplete {name} {basis}: missing {miss} - not posting from PDF")
            out["_keep"] = True
            return None
        quarters = [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 1), "m": prev}, None, None, {"q": rf.qlabel(q - 4), "m": yago}]
        empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
        for j in (2, 3):
            h = fx(q - j)
            quarters[j] = {"q": rf.qlabel(q - j), "m": h or empty}
        return {"basis": basis, "qcode": q, "quarters": quarters, "note": note, "inferred": q_head is None}
    return None
