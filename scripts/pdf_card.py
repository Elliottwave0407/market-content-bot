"""Fast path: read the filing PDF with Gemini, verify it, return card data. Returns None whenever anything is doubtful."""
import os, re, time
from datetime import datetime
import requests
import results_fetcher as rf
import gemini_read as gr

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-flash-lite-latest"
DAILY_CAP = int(os.environ.get("GEMINI_DAILY_CAP", "450"))
PER_POLL = int(os.environ.get("PDF_PER_POLL", "6"))
K = {"lakh": 0.1, "lakhs": 0.1, "lac": 0.1, "lacs": 0.1, "crore": 10.0, "crores": 10.0, "million": 1.0, "thousand": 0.001, "actual": 1e-6}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
TRIES, STATE_ = {}, {"backoff": 0.0, "calls": 0}
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
        res.append(tol(ti - ex, pbt))
    if None not in (pbt, tax, pat):
        res.append(tol(pbt - tax, pat))
    return bool(res) and all(res), len(res)

def to_m(d, i, k):
    rev, pbt, pat, eps = (val(d, x, i) for x in ("revenue", "pbt", "pat", "eps"))
    exp, dep, fin = (val(d, x, i) for x in ("total_expenses", "depreciation", "finance_costs"))
    ebitda = None
    if None not in (rev, exp, dep, fin) and rev and fin / rev < 0.25:
        ebitda = (rev - exp + dep + fin) * k
    sc = lambda v: None if v is None else v * k
    return {"revenue": sc(rev), "ebitda": ebitda, "pbt": sc(pbt), "pat": sc(pat), "eps": eps, "bank": False}

def close(a, b):
    return abs(a - b) <= max(0.6, 0.005 * abs(b))

def geminikey():
    return os.environ.get("GEMINI_API_KEY", "").strip()

def try_pdf(bse, rec, st, headline, filed):
    """-> dict(basis, qcode, quarters, verified_note, raw) or None."""
    key = geminikey()
    att = rec.get("ATTACHMENTNAME")
    nid = rec["NEWSID"]
    if not key or not att or os.environ.get("PDF_FAST", "1") != "1":
        return None
    if TRIES.get(nid, 0) >= 2 or time.time() < STATE_["backoff"] or STATE_["calls"] >= PER_POLL:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))
    use = st.setdefault("gem_use", {})
    if use.get(day, 0) >= DAILY_CAP:
        return None
    q_head = rf.expected_quarter(headline, filed)
    TRIES[nid] = TRIES.get(nid, 0) + 1
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
    STATE_["calls"] += 1
    use[day] = use.get(day, 0) + 1
    out, err = gr.read_pdf(key, MODEL, content, tries=1, timeout=90)
    if out is None:
        if err and "429" in err:
            STATE_["backoff"] = time.time() + 120
        LOG.append(f"pdf read failed {rec.get('SLONGNAME')}: {str(err)[:80]}")
        return None
    k = K.get(str(out.get("unit", "")).lower())
    cols = out.get("quarter_end_columns") or []
    qe = parse_qend(cols[0]) if cols else None
    if not k or qe is None:
        LOG.append(f"pdf unusable {rec.get('SLONGNAME')}: unit/date missing")
        return None
    q_pdf = rf.qcode(qe[0], qe[1])
    if q_head is not None and q_head != q_pdf:
        LOG.append(f"pdf quarter mismatch {rec.get('SLONGNAME')}")
        return None
    q = q_pdf
    for basis in ("consolidated", "standalone"):
        d = out.get(basis)
        if not d or val(d, "revenue", 0) is None or val(d, "pat", 0) is None:
            continue
        ok, n = arith_ok(d)
        cur, prev, yago = (to_m(d, i, k) for i in range(3))
        code, name = str(rec["SCRIP_CD"]), rec["SLONGNAME"]
        hist, hpat = {}, {}
        for off, m in ((1, prev), (4, yago)):
            h = rf.fetch(bse, code, name, basis, q - off)
            if h and h.get("revenue") is not None and m["revenue"] is not None:
                hist[off] = close(m["revenue"], h["revenue"])
            if h and h.get("pat") is not None and m["pat"] is not None:
                hpat[off] = abs(m["pat"] - h["pat"]) <= max(1.0, 0.03 * abs(h["pat"]))
        if hist and not all(hist.values()):
            LOG.append(f"pdf history mismatch {name} {basis}")
            continue
        strong = len(hist) == 2 and len(hpat) == 2 and all(hpat.values())
        if not ok and not strong:
            LOG.append(f"pdf checks failed {name} {basis}")
            continue
        if ok:
            note = "history-verified" if hist else "no BSE history (arithmetic-checked only)"
        else:
            note = "verified against BSE's previous quarters"
        r0, r1 = cur["revenue"], prev["revenue"]
        if r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50):
            return None
        quarters = [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 1), "m": prev}, None, None, {"q": rf.qlabel(q - 4), "m": yago}]
        empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
        for j in (2, 3):
            h = rf.fetch(bse, code, name, basis, q - j)
            quarters[j] = {"q": rf.qlabel(q - j), "m": h or empty}
        return {"basis": basis, "qcode": q, "quarters": quarters, "note": note, "inferred": q_head is None}
    return None
