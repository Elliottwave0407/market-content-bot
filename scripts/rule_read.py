"""Rule-based reader for result PDFs: pulls the numbers straight out of the PDF's own text layer (no AI, no quota, ~1 s).
Returns the same JSON shape as gemini_read (unit, quarter_end_columns, consolidated, standalone) so every existing check (column dates, BSE-history cross-check, size guard) still runs on it.
It ACCEPTS a table only when the statement reconciles by itself in all three columns (total income - expenses [- exceptional] = profit before tax, and profit before tax - tax [+ associates] = net profit).
Anything else returns (None, reason) and the caller falls back to Gemini / NVIDIA. Numbers are only ever copied from the PDF text (the tax line is summed from its printed parts if no total line exists)."""
import re
import os
import itertools

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
NUMRE = re.compile(r"^(\(\d[\d,]*(\.\d+)?\)|\(-\d[\d,]*(\.\d+)?\)|[-−–]?\d[\d,]*(\.\d+)?)[*#^]?$")
NILS = {"-", "–", "—", "−", "--", "nil", "NIL", "Nil"}
KEYS = ("revenue from operations", "total income", "profit before tax", "profit/(loss) before tax", "profit / (loss) before tax", "total expenses")
KEYNAMES = ("revenue", "other_income", "total_income", "total_expenses", "finance_costs", "depreciation", "exceptional", "pbt", "tax", "associates", "pat", "eps")


def _num(t):
    t = t.strip().rstrip("*#^")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").replace("−", "-").replace("–", "-")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg and v > 0 else v


def _isnum(w):
    return bool(NUMRE.match(w))


def _deskew(ws):
    """A scanned page that is a fraction of a degree off makes the numbers at the right end of a row sit a few points above or below
    its label, so label and numbers fall into different rows (15 Nov RCA: 'Total Income' and its figures split, Bhandari Hosiery).
    Find the tilt whose horizontal projection of word centres is sharpest and straighten the y values by it. Only applied when it
    clearly helps; a straight page is returned unchanged."""
    import math
    if len(ws) < 60:
        return ws
    xs = [(w[0] + w[2]) / 2 for w in ws]
    ys = [(w[1] + w[3]) / 2 for w in ws]
    hs = sorted(max(1.0, w[3] - w[1]) for w in ws)
    bin_ = max(1.0, hs[len(hs) // 2] * 0.5)
    x0 = sum(xs) / len(xs)

    def score(t):
        cnt = {}
        for x, y in zip(xs, ys):
            k = int((y - (x - x0) * t) / bin_)
            cnt[k] = cnt.get(k, 0) + 1
        return sum(c * c for c in cnt.values())

    base = score(0.0)
    best_t, best = 0.0, base
    for i in range(-30, 31):          # -1.5 .. +1.5 degrees in 0.05 steps
        t = math.tan(math.radians(i * 0.05))
        sc = score(t)
        if sc > best:
            best_t, best = t, sc
    if best_t == 0.0 or best < base * 1.05:
        return ws
    return [(w[0], w[1] - ((w[0] + w[2]) / 2 - x0) * best_t, w[2], w[3] - ((w[0] + w[2]) / 2 - x0) * best_t) + tuple(w[4:]) for w in ws]


def rows_of(page, rot=0):
    """Words of a page grouped into visual rows. rot 90 / 270: the page content is drawn sideways (landscape tables)."""
    ws0 = page.get_text("words")
    if not ws0:
        return []
    ws = []
    for w in ws0:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if rot == 0:
            ws.append(w)
        elif rot == 90:      # text runs bottom-to-top
            ws.append((-w[3], cx - (w[2] - w[0]) / 2, -w[1], cx + (w[2] - w[0]) / 2) + tuple(w[4:]))
        else:                # text runs top-to-bottom
            ws.append((w[1], -cx - (w[2] - w[0]) / 2, w[3], -cx + (w[2] - w[0]) / 2) + tuple(w[4:]))
    ws = _deskew(ws)
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows, cur, cy = [], [], None
    for w in ws:
        yc = (w[1] + w[3]) / 2
        h = max(1.0, w[3] - w[1])
        if cy is None or abs(yc - cy) <= 0.45 * h:
            cur.append(w)
            cy = yc if cy is None else (cy * (len(cur) - 1) + yc) / len(cur)
        else:
            rows.append(sorted(cur, key=lambda x: x[0]))
            cur, cy = [w], yc
    if cur:
        rows.append(sorted(cur, key=lambda x: x[0]))
    return rows


GARB = {}      # id(nums list) -> {position: raw OCR token} for numbers the OCR garbled (14 Nov, Kernex); only used by _assemble's strict, cross-checked repair
_GARBRE = re.compile(r"^[\(\[\{|!]?[0-9OoIlsSZ.,'`|]{3,}[\)\]\}|]?$")


def _tok(t):
    """A stray OCR mark glued to the front of a printed number ('«652.09') is dropped, only when what remains is a valid number."""
    u = t.lstrip("«»|!¦~`'\"")
    if u != t and u and _isnum(u):
        return u
    if not _isnum(t):
        v = t.rstrip(".,;:")      # '3,429.65.' : sentence dot after the last column
        if v != t and _isnum(v):
            return v
        m = re.match(r"^(\(?-?)(\d{1,3})((?:\.\d{3})+)(\.\d{1,2})(\)?)$", t)      # '2.212.22' : OCR wrote a dot for the thousands comma
        if m:
            w = m.group(1) + m.group(2) + m.group(3).replace(".", ",") + m.group(4) + m.group(5)
            if _isnum(w):
                return w
    return t


_PUNCT_ONLY = re.compile(r"^[|¦»«~!\[\]{}:;_'`‘’“”,*#=<>\\/]+$")


def split_row(row):
    # 15 Nov RCA: a lone border or punctuation mark ('|', ':', '»') sitting between or after the figures cut the row there and pushed the
    # earlier figures into the label, so the revenue row looked like it had 0-2 numbers (page filter rejected ~half of the skipped filings)
    toks = [_tok(w[4]) for w in row if not _PUNCT_ONLY.match(w[4])]
    i = len(toks)
    while i > 0 and (_isnum(toks[i - 1]) or toks[i - 1] in NILS):
        i -= 1
    garb = {}
    # one garbled number token between printed numbers (e.g. '6s2.09' for '652.09') used to cut the row and push the earlier numbers into the label: bridge it as an unknown value
    while i >= 2 and len(toks) - i >= 2 and not garb and _GARBRE.match(toks[i - 1]) and sum(ch.isdigit() for ch in toks[i - 1]) >= 2 and (_isnum(toks[i - 2]) or toks[i - 2] in NILS):
        garb[0] = toks[i - 1]
        i -= 1
        while i > 0 and (_isnum(toks[i - 1]) or toks[i - 1] in NILS):
            i -= 1
        break
    nums = [(_num(t) if _isnum(t) else None) for t in toks[i:]]
    if garb:
        # i now points before the numbers left of the garbled token: rebuild so the garbled token sits as None in its own position
        j = i
        seq = toks[j:]
        nums = []
        gpos = {}
        for t in seq:
            if _isnum(t):
                nums.append(_num(t))
            elif t in NILS:
                nums.append(None)
            else:
                gpos[len(nums)] = t
                nums.append(None)
        GARB[id(nums)] = gpos
        GARB.setdefault("_keep", []).append(nums)      # keep the list alive so its id stays unique
    return " ".join(toks[:i]).strip(), nums


def clean_label(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("lncome", "income").replace("incorne", "income")      # RapidOCR / tesseract read the capital I as l
    for _ in range(4):
        s2 = re.sub(r"^[\]\[|_{}~]+\s*", "", s)      # 15 Nov RCA: a ruled-table border read as '] Revenue from operations' / '| Revenue ...' hid the row
        s2 = re.sub(r"^[0-9a-z]{1,3}\s*_*\s*[\]\[|!]+\s*(?=[a-z(])", "", s2)      # '1_|revenue', 'i |revenue', '1 [revenue', '1 !revenue': enumerator + ruled-border mark
        s2 = re.sub(r"^(?:i{1,3}|iv)(?=(?:revenue|total))", "", s2)      # 'irevenue', 'iiitotal revenue': roman numeral glued to the label
        s2 = re.sub(r"^[a-h]\.\s+(?=[a-z(])", "", s2)      # 15 Nov RCA: 'a. Revenue from operations' (letter-dot enumerator) was not stripped, so the page filter rejected the results page (57 of 99 filings)
        s2 = re.sub(r"^(\(?[a-z]{1,2}\)|\(\d{1,2}\)|\([ivx]{1,4}\)|[ivx]{1,4}\)|\d{1,2}\.|\d{1,2}\)|[-–•*]+)\s*", "", s2)
        s2 = re.sub(r"^\d{1,2}\s+(?=[a-z(])", "", s2)
        s2 = re.sub(r"^(?:i{1,3}|iv|vi{0,3}|ix|x)(?:\.|\s)\s*(?=[a-z(])", "", s2)
        s2 = re.sub(r"^(add|less|plus)\s*[:\-]\s*", "", s2)
        s2 = re.sub(r"^(til|ill|iil|lll|ii1|il1|1ll|i11|ii|il|li|l|ll|i)\.?\s*(?=total )", "", s2)      # OCR misread of the roman numeral III before 'Total Income' (Kernex 14 Nov: 'til Total Income')
        if s2 == s:
            break
        s = s2
    return _fuzzy_label(s.strip(" :"))


_CANON = ("revenue from operations", "total income", "other income", "total expenses", "finance costs", "profit before tax", "tax expense", "profit for the period", "net profit for the period", "total tax expense", "depreciation and amortisation expense")
_CANON_A = {re.sub(r"[^a-z]", "", c_): c_ for c_ in _CANON}


def _fuzzy_label(r):
    """16 Nov (Ambika Cotton, scanned page read by OCR as 'RevenuefromCperalions'): a glued / garbled label is mapped to the canonical statement label when it is at least 90% similar to exactly one of them.
    Only labels that are not made of ordinary vocabulary words are touched, so real labels are never rewritten."""
    try:
        a = re.sub(r"[^a-z]", "", r)
        if a in _CANON_A and " " not in r:
            return _CANON_A[a]
        if len(a) < 9 or len(a) > 40 or a in _CANON_A:
            return r
        if " " in r and all(w in _VOCAB for w in re.findall(r"[a-z]+", r)):
            return r
        import difflib
        best = [(difflib.SequenceMatcher(None, a, k).ratio(), k) for k in _CANON_A if abs(len(k) - len(a)) <= 3]
        best = sorted([b for b in best if b[0] >= 0.9], reverse=True)
        if len(best) == 1 or (len(best) > 1 and best[0][0] - best[1][0] >= 0.05):
            return _CANON_A[best[0][1]]
    except Exception:
        pass
    return r


def _dates(text):
    hits = []
    mon = r"(jan[a-z]*|feb[a-z]*|mar[a-z]*|apr[a-z]*|may|jun[a-z]*|jul[a-z]*|aug[a-z]*|sep[a-z]*|oct[a-z]*|nov[a-z]*|dec[a-z]*)"
    pats = [
        (0, r"\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})\b"),
        (1, r"\b(\d{1,2})(?:st|nd|rd|th)?[\s.,-]*" + mon + r"[\s.,'-]*(\d{4})\b"),
        (2, r"\b" + mon + r"[\s.]*(\d{1,2})(?:st|nd|rd|th)?[\s,]*(\d{4})\b"),
    ]
    for pi, p in pats:
        for m in re.finditer(p, text, re.I):
            try:
                g = m.groups()
                if pi == 0: d, mo, y = int(g[0]), int(g[1]), int(g[2])
                elif pi == 1: d, mo, y = int(g[0]), MONTHS[g[1][:3].lower()], int(g[2])
                else: d, mo, y = int(g[1]), MONTHS[g[0][:3].lower()], int(g[2])
                if 1 <= d <= 31 and 1 <= mo <= 12 and 2000 <= y <= 2100:
                    hits.append((m.start(), f"{d:02d}.{mo:02d}.{y}"))
            except Exception:
                pass
    hits.sort()
    return [s for _, s in hits]


def _layout_ok(ds):
    ms = []
    for s in ds[:3]:
        _, mo, y = s.split(".")
        ms.append(int(y) * 12 + int(mo))
    return len(ms) == 3 and (ms[0] - ms[1], ms[0] - ms[2]) in ((3, 12), (12, 3)) and int(ds[0].split(".")[1]) in (3, 6, 9, 12)


def _qdates_from_code(q):
    n = int(q) - 129
    months = n * 3 + 3
    y = 2026 + (months - 1) // 12
    mo = (months - 1) % 12 + 1
    last = {3: 31, 6: 30, 9: 30, 12: 31}

    def sh(mm, yy, k):
        t = yy * 12 + (mm - 1) - k
        return t // 12, t % 12 + 1
    y1, m1 = sh(mo, y, 3)
    y2, m2 = sh(mo, y, 12)
    return [f"{last[mo]:02d}.{mo:02d}.{y}", f"{last[m1]:02d}.{m1:02d}.{y1}", f"{last[m2]:02d}.{m2:02d}.{y2}"]


def _units_in(text):
    """Distinct unit words in a table header (the rupee sign often decodes to a stray character, so only the unit word itself is used)."""
    found = set()
    for m in re.finditer(r"(crores?|\bcrs?\b|lakhs?|lacs?|millions?|\bmn\b|thousands?)", text.lower()):
        w = m.group(1)
        found.add("lakh" if w.startswith(("lakh", "lac")) else "crore" if w.startswith(("crore", "cr")) else "million" if w.startswith(("million", "mn")) else "thousand")
    return found


def _looks_like_table(rws):
    n = 0
    for r in rws:
        lb, nums = split_row(r)
        if len(nums) >= 3 and re.search(r"revenue|total income|income from operations|net sales|profit", lb.lower()):
            n += 1
    return n >= 2


class OcrPage:
    """Page-like object whose words come from tesseract (for scanned PDFs). Same get_text API the row builder uses."""
    def __init__(self, words):
        self._w = words

    def get_text(self, kind="text"):
        if kind == "words":
            return self._w
        return " ".join(w[4] for w in self._w)



_RAPID = {"eng": None, "bad": False}
_VOCAB = set("""revenue from operations operation other income total expenses expense cost costs of materials material consumed purchases purchase stock in trade changes inventories inventory finished goods work progress employee employees benefit benefits finance depreciation amortisation amortization and profit loss before after tax exceptional extraordinary items item for the period year quarter half ended months six three net sales comprehensive per equity share basic diluted earnings paid up capital face value reserves current deferred prior earlier years attributable owners non controlling interests minority associates joint ventures share associate consolidated standalone unaudited audited statement results financial continuing discontinued operation discontinuing ordinary activities interest on borrowings provisions provision write off exchange fluctuation gain gains losses fair measurement remeasurement defined plans that will not be reclassified to or items reclassified comprise comprising rs lakhs lakh crores crore million thousands amount in inr less add a an by with at as is are on net sale operating expenditure excess under over other liabilities assets investments investment subsidiaries impairment diminution value writeoff bad debts doubtful debts trade receivables written off january february march april may june july august september october november december sept ended statements particulars unlessstated unless stated otherwise amount rupees segment information notes regulation regulations listing obligations disclosure requirements limited ltd company private""".split())


def _segment(t):
    """RapidOCR drops the spaces inside long printed labels ('Revenuefromoperations'): put them back using the finance vocabulary. Anything not segmentable is returned unchanged."""
    if " " in t or len(t) < 9:
        return t
    if not t.isalpha():
        return re.sub(r"[A-Za-z]{9,}", lambda m: _segment(m.group(0)), t)
    low = t.lower(); n = len(low)
    best = [None] * (n + 1); best[0] = (0, [])
    for i in range(1, n + 1):
        for j in range(max(0, i - 14), i):
            if best[j] is None: continue
            w = low[j:i]
            if w in _VOCAB:
                sc = best[j][0] + len(w) ** 2
                if best[i] is None or sc > best[i][0]:
                    best[i] = (sc, best[j][1] + [(j, i)])
    if best[n] is None: return t
    return " ".join(t[a:b] for a, b in best[n][1])


def _rapid_words(pg, angle=0, dpi=200):
    """RapidOCR (PaddleOCR models on onnxruntime, free, CPU): far better than tesseract on ruled/shaded result tables. Returns (words, mean confidence) in the tesseract tuple format, or None if unavailable."""
    import numpy as np
    import fitz
    if _RAPID["bad"]:
        return None
    try:
        if _RAPID["eng"] is None:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID["eng"] = RapidOCR()
    except Exception:
        _RAPID["bad"] = True
        return None
    sc = dpi / 72.0
    pix = pg.get_pixmap(matrix=fitz.Matrix(sc, sc), colorspace=fitz.csRGB)
    im = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    if angle:
        im = np.ascontiguousarray(np.rot90(im, k=(angle // 90) % 4))
    res, _ = _RAPID["eng"](im)
    out, confs = [], []
    for box, txt, cf in (res or []):
        txt = txt.replace("|", " ").replace("\u20b9", "").strip()
        if not txt: continue
        xs = [q[0] for q in box]; ys = [q[1] for q in box]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        toks = [_segment(t) for t in txt.split()]
        toks = " ".join(toks).split()
        tot = sum(len(t) for t in toks) or 1; cx = x0
        for t in toks:
            wd = (x1 - x0) * len(t) / tot
            out.append((cx / sc, y0 / sc, (cx + wd) / sc, y1 / sc, t, 0, 0, 0)); cx += wd
        confs.append(float(cf) * 100)
    return out, (sum(confs) / len(confs) if confs else 0)


def _ocr_words(pg, angle=0, dpi=300):
    if os.environ.get("RULE_OCR_ENGINE") == "rapid":
        rw = _rapid_words(pg, angle)
        if rw is not None:
            return rw
    import subprocess, tempfile
    import fitz
    sc = dpi / 72.0
    pix = pg.get_pixmap(matrix=fitz.Matrix(sc, sc), colorspace=fitz.csGRAY)
    if angle:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(pix.tobytes("png"))).rotate(angle, expand=True)
        buf = io.BytesIO(); im.save(buf, "PNG"); data = buf.getvalue()
    else:
        data = pix.tobytes("png")
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "p.png")
        open(f, "wb").write(data)
        r = subprocess.run(["tesseract", f, "stdout", "--psm", "6", "-c", "preserve_interword_spaces=1", "tsv"], capture_output=True, text=True, timeout=60, env=dict(os.environ, OMP_THREAD_LIMIT="1"))
    out, confs = [], []
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            x, y, w, h, cf = int(c[6]), int(c[7]), int(c[8]), int(c[9]), float(c[10])
        except ValueError:
            continue
        if cf < 0:
            continue
        t = c[11].strip().replace("|", "").replace("₹", "")
        if not t:
            continue
        confs.append(cf)
        out.append((x / sc, y / sc, (x + w) / sc, (y + h) / sc, t, 0, 0, 0))
    # OCR often drops the decimal point ("23537" for 235.37): when the table prints 2 decimals almost everywhere, restore it. The reconcile gate still has the last word.
    dec = sum(1 for w in out if re.match(r"^[-(]?[\d,]+\.\d\d\)?$", w[4]))
    allnum = sum(1 for w in out if re.match(r"^[-(]?[\d,]+(\.\d+)?\)?$", w[4]))
    if allnum >= 20 and dec / allnum > 0.5:
        fixed = []
        for w in out:
            m = re.match(r"^(\(?-?)(\d{3,})(\)?)$", w[4])
            if m and not (len(m.group(2)) == 4 and 1990 <= int(m.group(2)) <= 2100):
                d = m.group(2)
                w = w[:4] + (m.group(1) + d[:-2] + "." + d[-2:] + m.group(3),) + w[5:]
            fixed.append(w)
        out = fixed
    return out, (sum(confs) / len(confs) if confs else 0)


def _pdf_rows(pdf_bytes, max_pages=14, ocr=False):
    import fitz
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, pg in enumerate(d):
        if i >= max_pages:
            break
        if ocr:
            ws, cf = _ocr_words(pg)
            op = OcrPage(ws)
            rws = rows_of(op)
            if not _looks_like_table(rws) and cf < 70:
                for ang in (90, 270):
                    ws2, cf2 = _ocr_words(pg, ang)
                    r2 = rows_of(OcrPage(ws2))
                    if _looks_like_table(r2):
                        rws, op = r2, OcrPage(ws2)
                        break
            pages.append((op.get_text("text"), rws))
            continue
        rws = rows_of(pg)
        if not _looks_like_table(rws):
            for rot in (90, 270):
                alt = rows_of(pg, rot)
                if _looks_like_table(alt):
                    rws = alt
                    break
        pages.append((pg.get_text("text"), rws))
    return pages


PAT_REV = [r"^total revenue from operations", r"^revenue from operations", r"^total income from operations", r"^income from operations",
           r"^net sales/income from operations", r"^net sales", r"^sales/income from operations", r"^sales\b", r"^revenue from operation"]


def _all_matches(rows, pats, start=0, avoid=(), n=None):
    out = []
    for p in pats:
        for i in range(start, len(rows)):
            lb, nums, cands = rows[i]
            if len(nums) < 3 or (n is not None and len(nums) != n):
                continue
            if all(v is None for v in nums[:3]) and not any("tax" in c for c in cands):
                continue
            if any(re.search(p, c) and not any(re.search(a, c) for a in avoid) for c in cands):
                if all(i != j for j, _ in out):
                    out.append((i, nums))
    return out


def _candidates(rows):
    rv = _all_matches(rows, PAT_REV, avoid=("other operating", "segment"))
    if not rv:
        return None
    n = len(rv[0][1])
    c = {"revenue": rv[:1]}
    c["total_income"] = _all_matches(rows, [r"^total income\b(?! from operations)", r"^total revenue\b(?! from operations)"], n=n, avoid=("from operations", "segment"))[:1]
    c["other_income"] = _all_matches(rows, [r"^other income"], n=n)[:1]
    # 16 Nov (Biocon, BF Investment, AJR Infra): the first revenue-like row can be a sub-line. Pick the revenue row that ties to total income (revenue + other income = total income, current column).
    # Only when none ties AND the row is far below total income - other income, replace it by that difference. Nil-revenue statements (revenue, other income and total income rows all identical) give revenue 0.
    # Kept narrow: a wider fallback broke Hilinfra, Banarisug and Gaudium IVF in the replay (small gaps are real other operating revenue lines).
    if c["total_income"] and rv:
        t0 = c["total_income"][0][1][0]
        oi_ = c["other_income"][0][1] if c["other_income"] else None
        o0 = None if oi_ is None else oi_[0]
        r0 = rv[0][1][0]
        if t0 is not None and r0 is not None and t0 > 0:
            if o0 is not None and abs(o0 - t0) <= 0.003 * t0 and abs(r0 - t0) <= 0.003 * t0:
                c["revenue"] = [(rv[0][0], [0.0 if x is not None else None for x in rv[0][1]])]
            else:
                oo = o0 or 0.0
                ok = [r_ for r_ in rv if r_[1][0] is not None and abs(r_[1][0] + oo - t0) <= max(0.003 * t0, 0.6)]
                if ok:
                    c["revenue"] = ok[:1]
                elif r0 < (t0 - oo) - 0.05 * t0 and (o0 is None and r0 < 0.75 * t0 or o0 is not None and o0 < 0.5 * t0):
                    ti_ = c["total_income"][0][1]
                    oiv = oi_ if oi_ is not None else [0.0] * len(ti_)
                    c["revenue"] = [(rv[0][0], [None if (x is None) else round(x - (y or 0.0), 2) for x, y in zip(ti_, oiv)])]
    if c["total_income"] and c["revenue"]:      # 16 Nov (Aprameya): a printed number that lost its decimal point (171253 for 1,712.53) shows up as revenue far above total income; repair it only when the shifted value ties exactly to total income - other income
        tv, rvv = c["total_income"][0][1], list(c["revenue"][0][1])
        ov = c["other_income"][0][1] if c["other_income"] else [0.0] * len(tv)
        for j in range(min(len(tv), len(rvv), len(ov))):
            if rvv[j] is not None and tv[j] and rvv[j] > tv[j] * 1.001:
                for k_ in (10, 100, 1000):
                    if abs(rvv[j] / k_ + (ov[j] or 0.0) - tv[j]) <= max(0.003 * abs(tv[j]), 0.6):
                        rvv[j] = round(rvv[j] / k_, 2); break
        c["revenue"] = [(c["revenue"][0][0], rvv)]
    c["total_expenses"] = _all_matches(rows, [r"^total expenses", r"^total expenditure"], n=n)[:1]
    c["finance_costs"] = _all_matches(rows, [r"^finance costs?", r"^financial costs?", r"^finance cost\b", r"^interest and finance", r"^finance charges", r"^interest expenses?"], n=n)[:1]
    c["depreciation"] = _all_matches(rows, [r"^depreciation", r"^amortisation|^amortization"], n=n)[:1]
    c["exceptional"] = _all_matches(rows, [r"^exception"], n=n)[:1]
    pbs = _all_matches(rows, [r"before tax", r"before income tax"], n=n, avoid=("exceptional", "extraordinary", "associate", "joint venture", "share of", "discontinued"))
    pbs += _all_matches(rows, [r"before exceptional.{0,30}tax", r"before extraordinary.{0,30}tax", r"before exceptional items and tax"], n=n, avoid=("associate", "share of", "discontinued"))
    c["pbt"] = pbs[:3]
    start = pbs[0][0] if pbs else 0
    tx = _all_matches(rows, [r"^total tax expenses?", r"^tax expenses?", r"^total income tax", r"^income tax expenses?", r"^total tax", r"^provision for (income )?tax", r"^tax$"], start=max(0, start - 1), n=n, avoid=("before", "deferred tax asset", "relating to"))
    if not tx:      # 14 Nov (Kernex): OCR lost one printed number of the total-tax row; accept it left-aligned only if the statement then reconciles in all three columns (checked later)
        tx = [(i_, nm_) for i_, nm_ in _all_matches(rows, [r"^total tax expenses?", r"^total tax", r"^tax expenses?", r"^total income tax"], start=max(0, start - 1), avoid=("before", "deferred tax asset", "relating to")) if n - 2 <= len(nm_) < n]
    c["tax"] = tx[:1]
    c["associates"] = _all_matches(rows, [r"share of (net )?\(?(profit|loss).{0,60}(associate|joint)", r"share in (profit|loss).{0,40}(associate|joint)"], n=n, avoid=("before", "after share", "attributable"))[:1]      # 15 Nov (AIA Engineering): the subtotal 'Profit BEFORE share of profit of joint venture, exceptional item and tax' was taken as the associates figure, so consolidated never reconciled
    pi = pbs[0][0] if pbs else 0
    pats = _all_matches(rows, [r"(profit|loss).{0,45}(for the (period|quarter|year|half)|after tax|after taxes)", r"(profit|loss).{0,30}continuing operations"], start=pi + 1, n=n,
                        avoid=("before", "attributable", "comprehensive", "owners", "non-controlling", "minority", "per share", "discontinued", "other equity", "reserve", "total profit"))
    pats = [x for x in pats if not re.search(r"^(add|less)\b", clean_label(rows[x[0]][0]))]
    if not pats:
        pats = [(i_, nm_) for i_, nm_ in _all_matches(rows, [r"(profit|loss).{0,45}(for the (period|quarter|year|half)|after tax|after taxes)"], start=pi + 1,
                        avoid=("before", "attributable", "comprehensive", "owners", "non-controlling", "minority", "per share", "discontinued", "other equity", "reserve", "total profit")) if n - 2 <= len(nm_) < n]
    c["pat"] = pats[:4]
    pj = pats[0][0] if pats else pi
    c["eps"] = _all_matches(rows, [r"\bbasic\b", r"^earnings? per (equity )?share", r"^eps\b"], start=pj + 1, n=n)[:1]
    return c, n


def _tol(a, b, unit):
    return abs(a - b) <= max(0.0025 * max(abs(a), abs(b)), 0.15 if unit == "crore" else 0.6)


import threading
_RELAX = threading.local()      # half-year statements: tax sub-rows often sit in the wrong column (Anondita), so PAT only has to be sane versus PBT (same rule as sme_half.sme_ok); total income - expenses = PBT stays exact


def _col_status(d, i, unit):
    g = lambda k: (d.get(k) or [None] * 3)[i]
    ti, ex, pbt, tax, pat = g("total_income"), g("total_expenses"), g("pbt"), g("tax"), g("pat")
    exc, dp, fn, asc = g("exceptional"), g("depreciation"), g("finance_costs"), g("associates")
    if None in (ti, ex, pbt, tax, pat):
        return None
    e = [0.0] if exc in (None, 0.0) else [exc, -exc]
    a = [0.0] if asc in (None, 0.0) else [asc, -asc]      # 16 Nov (Alpex Solar): 'Share of (Profit) Loss of Associates' is printed with the opposite sign (-6.58 = a profit of 6.58); the exact arithmetic picks the sign, the share is never ignored      # 14 Nov (Raideep): with a non-zero share of associates the headline profit must INCLUDE it; accepting [asc, 0.0] let the pre-associates profit pass (5.23 instead of 48.32)
    def _c1(extra):
        return any(_tol(ti - ex + x + extra, pbt, unit) for x in e) or (None not in (dp, fn) and any(_tol(ti - ex - dp - fn + x + extra, pbt, unit) for x in e))
    c1 = _c1(0.0)
    c2 = any(_tol(pbt - tax + y, pat, unit) for y in a)
    if asc not in (None, 0.0) and not (c1 and c2):
        # 15 Nov (AIA Engineering): some statements show the share of joint ventures / associates ABOVE profit before tax (so PBT already includes it: total income - expenses + share = PBT, PBT - tax = PAT).
        # The share must be counted exactly once, in one place or the other, so the Raideep rule (never ignore a non-zero share) still holds.
        if (_c1(asc) or _c1(-asc)) and any(_tol(pbt - tax, pat, unit) for _ in (0,)):
            c1 = c2 = True
    if not c2 and getattr(_RELAX, "on", False) and asc in (None, 0.0):
        c2 = (pbt > 0 and -0.3 * pbt <= pat <= 1.6 * pbt) or (pbt <= 0 and pat <= 0.5 * abs(pbt) + 1.5)
    return bool(c1 and c2)


def _near(a, b):
    """True when digit strings a and b differ by at most one wrong, missing or extra digit (OCR noise), and are long enough to mean something."""
    if len(a) < 4 or len(b) < 4 or abs(len(a) - len(b)) > 1:
        return False
    if a == b:
        return True
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s_, l_ = (a, b) if len(a) < len(b) else (b, a)
    return any(l_[:k] + l_[k + 1:] == s_ for k in range(len(l_)))


def _assemble(cands, n, unit, rows):
    """Try the candidate rows (pbt / pat / tax variants) until the current column reconciles; returns (d, ok, unverified offsets)."""
    keys = [k for k in KEYNAMES if cands.get(k)]
    if "revenue" not in keys or "pat" not in keys:
        return None
    z = lambda lst: [0.0 if v is None else v for v in lst]
    pad = lambda lst: (list(lst[:3]) + [None] * 3)[:3]
    base = {k: pad(cands[k][0][1]) for k in keys if k not in ("pbt", "pat", "tax")}
    for k in ("exceptional", "associates"):
        if k in base:
            base[k] = z(base[k])
    first = None
    for pb, pt in itertools.product(cands.get("pbt") or [None], cands["pat"]):
        taxopts = [pad(z(t[1])) for t in (cands.get("tax") or [])]
        if pb is not None:
            parts, garbled = [], False
            for j in range(pb[0] + 1, pt[0]):
                lb, nums, cl = rows[j]
                if any(re.search(r"^(current|deferred|earlier|prior|short|excess|adjustment|mat credit|tax of|tax relating|income tax|taxes)", x) and "total" not in x for x in cl):
                    if len(nums) == n: parts.append(nums)
                    elif 1 <= len(nums) < n: parts.append([None] * (n - len(nums)) + list(nums))      # a row whose nil dashes were lost: its printed numbers sit at the right-hand columns
                    else: garbled = True
            if parts and not garbled:
                taxopts.append(pad([sum((p[k] or 0.0) for p in parts) for k in range(n)]))
        # 16 Nov (BTML): statements that print expenses as negatives show the tax rows as -60.48 / -4.40; the sign-flipped option is tried too, and the arithmetic (PBT - tax = PAT in all three columns) decides which one is right
        taxopts += [pad([None if v is None else -v for v in t]) for t in list(taxopts) if all((v or 0.0) <= 0 for v in t) and any((v or 0.0) < 0 for v in t)]
        for tx in taxopts or [None]:
            d = dict(base)
            d["pbt"] = pad(pb[1]) if pb else [None] * 3
            d["pat"] = pad(pt[1])
            if tx is not None:
                d["tax"] = tx
            gz = GARB.get(id(pt[1])) or {}
            if gz and tx is not None and pb is not None and all(v in (None, 0.0) for v in (d.get("associates") or [None])):
                pv = list(d["pat"])
                for gi, tok in gz.items():
                    if gi in (1, 2) and gi < 3 and pv[gi] is None and None not in (d["pbt"][gi], tx[gi]):
                        dv = round(d["pbt"][gi] - tx[gi], 2)
                        a_ = re.sub(r"\D", "", tok)
                        b_ = re.sub(r"\D", "", f"{abs(dv):.2f}")
                        if _near(a_, b_):
                            pv[gi] = dv
                d["pat"] = pv
            if first is None:
                first = d
            st0 = _col_status(d, 0, unit)
            if st0:
                unv = [off for off, i in ((1, 1), (4, 2)) if _col_status(d, i, unit) is not True]
                return d, True, unv
    return (first if first is not None else dict(base, pbt=[None] * 3, pat=pad(cands["pat"][0][1]))), False, []

_FAIL = threading.local()      # the last failed assembly per basis, kept so the text read and the OCR read can be merged cell by cell (19 Nov, Ansal: text garbled the tax cell, OCR garbled the PBT row; every printed figure was right in one source or the other)


def _snap():
    return {"d": dict(getattr(_FAIL, "d", {}) or {}), "ds": getattr(_FAIL, "ds", None), "unit": getattr(_FAIL, "unit", None), "half": getattr(_FAIL, "half", True), "cons": getattr(_FAIL, "cons", True)}


def _merge(a, b):
    """Merge a text-layer read and an OCR read of the SAME filing for the standalone table. Accepted only when every column reconciles exactly, and the current column's revenue, total income and PAT were read identically by both sources (an independent confirmation). -> result json or None."""
    if os.environ.get("RULE_MERGE", "0") != "1":      # 19 Nov: OFF by default - the replay showed one wrong merged read (Lovable: revenue 5.78 against 330.1 in XBRL); back on only after that case is understood
        return None
    if a["half"] or b["half"] or a["cons"] or b["cons"] or not a["ds"] or a["unit"] != b["unit"]:
        return None
    da, db = a["d"].get("standalone"), b["d"].get("standalone")
    if not da or not db or "consolidated" in a["d"] or "consolidated" in b["d"]:
        return None
    first = lambda d, k: (d.get(k) or [None])[0]
    for k in ("revenue", "total_income", "pat"):
        if first(da, k) is None or first(da, k) != first(db, k):
            return None
    ks = ("total_income", "total_expenses", "pbt", "tax", "pat")
    for pick in itertools.product((0, 1), repeat=len(ks)):
        dm = dict(da)
        for k, w in zip(ks, pick):
            dm[k] = list((da, db)[w].get(k) or [None] * 3)
        for k in ("exceptional", "associates", "depreciation", "finance_costs"):
            if not any(v is not None for v in (da.get(k) or [])) and db.get(k):
                dm[k] = db[k]
        if all(_col_status(dm, i, a["unit"]) is True for i in range(3)):
            out = {"unit": a["unit"], "quarter_end_columns": a["ds"], "consolidated": None, "standalone": dm, "_rule": True, "_rule_ok": {"standalone": True}, "_printed": {"standalone": 0}, "_half": False, "_unverified": {"standalone": []}, "_merged": True, "_ocr": True}
            for k in KEYNAMES:
                dm.setdefault(k, [None, None, None])
            dm.pop("exceptional", None); dm.pop("associates", None)
            return out
    return None


def read_pdf(pdf_bytes, hint="", qhint=None, allow_half=False):
    """Text layer first; if that fails, OCR the pages (scanned / garbled PDFs) and run the same strict reconcile gate."""
    r, why = _read(pdf_bytes, hint, qhint, False, allow_half)
    if r is not None or why is None:
        return r, why
    snap_t = _snap()
    import shutil
    if not shutil.which("tesseract") or os.environ.get("RULE_OCR", "0") != "1":
        return None, why
    if not re.search(r"no text layer|no results table|unit not found|header has no quarter|column dates|does not reconcile|incomplete|missing|no revenue row|columns|not read|ambiguous|unusual", why):      # a garbled text layer (digits and decimal marks split, e.g. Tonbo 5 Nov) misreads numbers and then fails to reconcile: the OCR read goes through the same strict gate
        return None, why      # text layer was readable: OCR would not fix a table that does not add up
    try:
        r2, why2 = _read(pdf_bytes, hint, qhint, True, allow_half)
    except Exception as e:
        return None, why + " | ocr err " + repr(e)[:60]
    if r2 is not None:
        r2["_ocr"] = True
        return r2, None
    try:
        m_ = _merge(snap_t, _snap())
    except Exception:
        m_ = None
    if m_ is not None:
        return m_, None
    return None, why + " | ocr: " + str(why2)[:420]


def _read(pdf_bytes, hint="", qhint=None, ocr=False, allow_half=False):
    """-> (json, None) or (None, reason). qhint: BSE quarter code from the filing headline (used for the column dates when the header cannot be read)."""
    try:
        pages = _pdf_rows(pdf_bytes, ocr=ocr)
    except Exception as e:
        return None, f"rule: pdf open failed {repr(e)[:50]}"
    if not pages:
        return None, "rule: empty pdf"
    if len(re.sub(r"\W", "", "".join(t for t, _ in pages))) < 400:
        return None, "rule: no text layer"
    blocks = {"standalone": [], "consolidated": []}
    basis = None
    htxt, first_page_txt, table_txt = "", "", ""
    first = True
    prev_table = False
    CONT = KEYS + ("tax expense", "net profit", "earnings per share", "basic")
    for pno, (txt, rws) in enumerate(pages):
        low = txt.lower()
        built = []
        for r in rws:
            lb, nums = split_row(r)
            built.append([lb, nums, [clean_label(lb)]])
        for i in range(len(built)):
            lb, nums, c = built[i]
            if nums and i > 0 and not built[i - 1][1] and not built[i - 1][0].rstrip().endswith(":") and len(clean_label(lb)) <= 18:
                c.append(clean_label(built[i - 1][0] + " " + lb))
            if nums and i + 1 < len(built) and not built[i + 1][1] and len(clean_label(built[i + 1][0])) <= 18 and not lb.rstrip().endswith(":"):
                c.append(clean_label(lb + " " + built[i + 1][0]))
        has_rev = any(len(n_) >= 3 and any(re.search(p, x) for x in c_ for p in PAT_REV) for _, n_, c_ in built)
        if not (has_rev and sum(k in low for k in KEYS) >= 2) and not (prev_table and sum(k in low for k in CONT) >= 2):
            prev_table = False
            continue
        prev_table = True
        if has_rev:      # header of each statement start: the text above its first revenue row
            hdr = []
            for lb_, nums_, c_ in built:
                if len(nums_) >= 3 and any(re.search(p_, x_) for x_ in c_ for p_ in PAT_REV):
                    break
                hdr.append(lb_)
            table_txt += " " + " ".join(hdr)
        for lb, nums, c in built:
            if (not nums or (len(nums) <= 2 and all(v is not None and (1990 <= abs(v) <= 2100 or v in range(1, 32)) for v in nums))) and 3 < len(lb) < 170:      # 14 Nov: a title ending '... September 30, 2026' has the day number too (Kernex: its consolidated page was filed under standalone)
                l = lb.lower().strip()
                a, b = bool(re.search(r"\bstandalone\b", l)), bool(re.search(r"\bconsolidated\b", l))
                title = ("statement" in l or "financial result" in l or "financial resu" in l or "results" in l) and "notes" not in l
                bare = re.match(r"^\(?(standalone|consolidated)\)?( financial)?( results)?$", l)
                if a != b and (title or bare):
                    basis = "standalone" if a else "consolidated"
            blocks[basis or "standalone"].append((lb, nums, c))
        if first:
            first = False
            first_page_txt = txt
            head = []
            for lb, nums, c in built:
                if len(nums) >= 3 and any(re.search(p, x) for x in c for p in PAT_REV):
                    break
                head.append(lb)
            htxt = " ".join(head)
    if first:
        return None, "rule: no results table page"
    low = htxt.lower()
    _RELAX.on = False
    half_mode = False
    if not re.search(r"quarter|three months|3 months", low + " " + first_page_txt[:2500].lower()):
        if allow_half and re.search(r"half[ -]?year(?:ly)? ended|for the half[ -]?year|half[ -]?yearly", low + " " + first_page_txt[:2500].lower()):
            half_mode = True; _RELAX.on = True      # 15 Nov: SME half-yearly statements: first three number columns are current half | preceding half | same half last year
        else:
            return None, "rule: header has no quarter columns"
    us = _units_in(table_txt)
    if len(us) != 1:
        return None, "rule: unit " + ("ambiguous " + str(sorted(us)) if us else "not found")
    unit = next(iter(us))
    ds = _dates(htxt)
    if half_mode:
        def _mi(t): return int(t.split(".")[2]) * 12 + int(t.split(".")[1])
        def _dt(m): return f"{30 if (m - 1) % 12 + 1 in (6, 9) else 31:02d}.{(m - 1) % 12 + 1:02d}.{(m - 1) // 12}"
        cur = None
        hd = [d_ for d_ in ds if int(d_.split(".")[1]) in (3, 9)]
        if len(hd) >= 3 and (_mi(hd[0]) - _mi(hd[1]), _mi(hd[0]) - _mi(hd[2])) == (6, 12):
            cur = hd[0]
        elif len(hd) >= 3 and sorted([_mi(hd[0]), _mi(hd[1]), _mi(hd[2])], reverse=True)[0] - sorted([_mi(hd[0]), _mi(hd[1]), _mi(hd[2])])[0] == 12:
            return None, "rule: half-year columns are in an unusual order"
        if cur is None and qhint is not None:
            qc_ = _qdates_from_code(qhint)
            if int(qc_[0].split(".")[1]) in (3, 9): cur = qc_[0]
        if cur is None:
            mm = re.search(r"ended\s*(?:on\s*)?([^\n]{0,28})", low + " " + first_page_txt[:2500].lower())
            dd_ = _dates(mm.group(1)) if mm else []
            if dd_ and int(dd_[0].split(".")[1]) in (3, 9): cur = dd_[0]
        if cur is None:      # last resort: the latest half-year-end date printed on the statement page (title 'AS AT 30 SEP 2026', 'Half year ended September 30, 2026')
            cand = [d_ for d_ in _dates(first_page_txt[:3500] + " " + htxt) if int(d_.split(".")[1]) in (3, 9)]
            if cand: cur = max(cand, key=_mi)
        if cur is None:
            return None, "rule: half-year column dates not found"
        ds = [cur, _dt(_mi(cur) - 6), _dt(_mi(cur) - 12)]
    elif not (len(ds) >= 3 and _layout_ok(ds)):
        ds = []
        qd = None
        for src in (htxt, first_page_txt[:3000], hint):
            m = re.search(r"(?:quarter|three months)[^.\n]{0,45}?ended\s*(?:on\s*)?([^\n]{0,28})", src, re.I)
            dd = _dates(m.group(1)) if m else []
            if dd and int(dd[0].split(".")[1]) in (3, 6, 9, 12):
                qd = dd[0]; break
        qc = _qdates_from_code(qhint) if qhint is not None else []
        if qd and qc and qd != qc[0]:
            return None, "rule: title quarter differs from the headline quarter"
        if qc:
            ds = qc
        elif qd:
            d_, mo_, y_ = qd.split(".")
            mo_, y_ = int(mo_), int(y_)
            code_ = 129 + ((y_ - 2026) * 12 + (mo_ - 3)) // 3
            ds = _qdates_from_code(code_)
    if not ds:
        return None, "rule: column dates not found"
    out = {"unit": unit, "quarter_end_columns": ds[:3], "consolidated": None, "standalone": None, "_rule": True, "_rule_ok": {}, "_printed": {}, "_half": half_mode}
    _FAIL.d = {}; _FAIL.ds = ds[:3]; _FAIL.unit = unit; _FAIL.half = half_mode
    _FAIL.cons = bool(re.search(r"statement of consolidated|consolidated (un)?audited financial results|consolidated financial results", " ".join(t for t, _ in pages).lower()))
    why = []
    for b in ("consolidated", "standalone"):
        rows = blocks[b]
        if not rows:
            continue
        cc = _candidates(rows)
        if not cc:
            why.append(f"{b[:4]}: no revenue row")
            continue
        cands, n = cc
        if n > 9:
            why.append(f"{b[:4]}: {n} columns")
            if b == "consolidated": return None, "rule: consolidated has " + str(n) + " columns"
            continue
        r = _assemble(cands, n, unit, rows)
        if r is None:
            why.append(f"{b[:4]}: missing {[k for k in ('revenue', 'pat') if not cands.get(k)]} n={n}")
            if b == "consolidated": return None, f"rule: consolidated table incomplete missing {[k for k in ('revenue', 'pat') if not cands.get(k)]} n={n}"
            continue
        d, ok, unv = r
        rv_ = cands["revenue"][0][1]
        if ok and not half_mode and n >= 4 and None not in (rv_[0], rv_[3]) and rv_[0] > 0 and rv_[3] > 0:
            if rv_[0] > rv_[3] * 1.02:
                ok = False; why.append(f"{b[:4]}: first column larger than the year-to-date column")
            elif n >= 5 and ds[0].split(".")[1] == "09" and rv_[1] is not None and abs(rv_[3] - rv_[0] - rv_[1]) > 0.02 * rv_[3]:
                _hs = f"{rv_[3]:.2f}".rstrip("0").rstrip(".")
                _fix = [float(c_ + _hs[1:]) for c_ in "1" if len(_hs) > 1 and _hs[0] in "47" and abs(float(c_ + _hs[1:]) - rv_[0] - rv_[1]) <= 0.002 * (rv_[0] + rv_[1])]
                if not _fix:
                    ok = False; why.append(f"{b[:4]}: half-year column is not quarter + previous quarter")
        if not ok:
            det = " ".join(f"{k}={d.get(k)}" for k in ("total_income", "total_expenses", "exceptional", "pbt", "tax", "associates", "pat", "depreciation", "finance_costs") if d.get(k))
            why.append(f"{b[:4]}: does not reconcile [{unit}] {det}")
            _FAIL.d[b] = d
            if b == "consolidated": return None, f"rule: consolidated table does not reconcile [{unit}] {det}"
            continue
        for k in KEYNAMES:
            d.setdefault(k, [None, None, None])
        e = d.pop("exceptional", None)
        d.pop("associates", None)
        out[b] = d
        out["_rule_ok"][b] = True
        out["_printed"][b] = 0
        out.setdefault("_unverified", {})[b] = unv
    if not out["consolidated"] and not out["standalone"]:
        return None, "rule: " + "; ".join(why or ["no results table recognised"])
    if not out["consolidated"]:
        alltxt = " ".join(t for t, _ in pages).lower()
        if re.search(r"statement of consolidated|consolidated (un)?audited financial results|consolidated financial results", alltxt):
            return None, "rule: filing mentions consolidated results but that table was not read"
    return out, None
