"""Rule-based reader for result PDFs: pulls the numbers straight out of the PDF's own text layer (no AI, no quota, ~1 s).
Returns the same JSON shape as gemini_read (unit, quarter_end_columns, consolidated, standalone) so every existing check (column dates, BSE-history cross-check, size guard) still runs on it.
It ACCEPTS a table only when the statement reconciles by itself in all three columns (total income - expenses [- exceptional] = profit before tax, and profit before tax - tax [+ associates] = net profit).
Anything else returns (None, reason) and the caller falls back to Gemini / NVIDIA. Numbers are only ever copied from the PDF text (the tax line is summed from its printed parts if no total line exists)."""
import re
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


def rows_of(page):
    ws = page.get_text("words")
    if not ws:
        return []
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


def split_row(row):
    toks = [w[4] for w in row]
    i = len(toks)
    while i > 0 and (_isnum(toks[i - 1]) or toks[i - 1] in NILS):
        i -= 1
    nums = [(_num(t) if _isnum(t) else None) for t in toks[i:]]
    return " ".join(toks[:i]).strip(), nums


def clean_label(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(4):
        s2 = re.sub(r"^(\(?[a-z]{1,2}\)|\([ivx]{1,4}\)|[ivx]{1,4}\)|\d{1,2}\.|\d{1,2}\)|[-–•*]+)\s*", "", s)
        s2 = re.sub(r"^\d{1,2}\s+(?=[a-z(])", "", s2)
        s2 = re.sub(r"^(?:i{1,3}|iv|vi{0,3}|ix|x)(?:\.|\s)\s*(?=[a-z(])", "", s2)
        s2 = re.sub(r"^(add|less|plus)\s*[:\-]\s*", "", s2)
        if s2 == s:
            break
        s = s2
    return s.strip(" :")


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


def _unit(text):
    m = re.search(r"(lakhs?|lacs?|crores?|\bcrs?\b|millions?|\bmn\b|thousands?|'000)", text.lower())
    if not m:
        return None
    w = m.group(1)
    if w.startswith(("lakh", "lac")): return "lakh"
    if w.startswith(("crore", "cr")): return "crore"
    if w.startswith(("million", "mn")): return "million"
    return "thousand"


def _pdf_rows(pdf_bytes, max_pages=14):
    import fitz
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, pg in enumerate(d):
        if i >= max_pages:
            break
        pages.append((pg.get_text("text"), rows_of(pg)))
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
    c["total_expenses"] = _all_matches(rows, [r"^total expenses", r"^total expenditure"], n=n)[:1]
    c["finance_costs"] = _all_matches(rows, [r"^finance costs?", r"^interest and finance", r"^finance charges", r"^interest expenses?"], n=n)[:1]
    c["depreciation"] = _all_matches(rows, [r"^depreciation", r"^amortisation|^amortization"], n=n)[:1]
    c["exceptional"] = _all_matches(rows, [r"^exceptional"], n=n)[:1]
    pbs = _all_matches(rows, [r"before tax", r"before income tax"], n=n, avoid=("exceptional", "extraordinary", "associate", "joint venture", "share of", "discontinued"))
    pbs += _all_matches(rows, [r"before exceptional.{0,30}tax", r"before extraordinary.{0,30}tax", r"before exceptional items and tax"], n=n, avoid=("associate", "share of", "discontinued"))
    c["pbt"] = pbs[:3]
    start = pbs[0][0] if pbs else 0
    tx = _all_matches(rows, [r"^total tax expenses?", r"^tax expenses?", r"^total income tax", r"^income tax expenses?", r"^total tax", r"^provision for (income )?tax", r"^tax$"], start=max(0, start - 1), n=n, avoid=("before", "deferred tax asset", "relating to"))
    c["tax"] = tx[:1]
    if not tx:      # sum printed parts under a "Tax expense" heading
        for i in range(max(0, start - 1), len(rows)):
            lb, nums, cands = rows[i]
            if not nums and any(re.search(r"^tax expenses?|^income tax", x) for x in cands):
                parts = []
                for j in range(i + 1, min(i + 8, len(rows))):
                    l2, n2, c2 = rows[j]
                    if len(n2) == n and any(re.search(r"current|deferred|earlier|prior|short|excess|\bmat\b", x) for x in c2):
                        parts.append(n2)
                    elif parts:
                        break
                if parts:
                    c["tax"] = [(i, [sum((p[k] or 0.0) for p in parts) for k in range(n)])]
                break
    c["associates"] = _all_matches(rows, [r"share of (net )?(profit|loss).{0,60}(associate|joint)", r"share in (profit|loss).{0,40}(associate|joint)"], n=n)[:1]
    pi = pbs[0][0] if pbs else 0
    pats = _all_matches(rows, [r"^(net )?profit.{0,40}for the (period|quarter|year)", r"^(net )?(profit|loss).{0,30}for the (period|quarter|year)", r"^profit.{0,12}after tax", r"^(net )?profit.{0,30}after tax",
                               r"^(net )?profit.{0,40}continuing operations"], start=pi + 1, n=n,
                        avoid=("before", "attributable", "comprehensive", "owners", "non-controlling", "minority", "per share"))
    c["pat"] = pats[:4]
    pj = pats[0][0] if pats else pi
    c["eps"] = _all_matches(rows, [r"\bbasic\b", r"^earnings? per (equity )?share", r"^eps\b"], start=pj + 1, n=n)[:1]
    return c, n


def _tol(a, b, unit):
    return abs(a - b) <= max(0.0025 * max(abs(a), abs(b)), 0.15 if unit == "crore" else 0.6)


def _chk(d, unit):
    """True if every column that can be tested reconciles; False if one fails; None if the current column cannot be tested."""
    tested0 = False
    for i in range(3):
        g = lambda k: (d.get(k) or [None] * 3)[i]
        ti, ex, pbt, tax, pat = g("total_income"), g("total_expenses"), g("pbt"), g("tax"), g("pat")
        exc, dp, fn, asc = g("exceptional"), g("depreciation"), g("finance_costs"), g("associates")
        if None in (ti, ex, pbt, tax, pat):
            if i == 0:
                return None
            continue
        e = [0.0] if exc in (None, 0.0) else [exc, -exc]
        a = [0.0] if asc in (None, 0.0) else [asc, 0.0]
        c1 = any(_tol(ti - ex + x, pbt, unit) for x in e) or (None not in (dp, fn) and any(_tol(ti - ex - dp - fn + x, pbt, unit) for x in e))
        c2 = any(_tol(pbt - tax + y, pat, unit) for y in a)
        if not (c1 and c2):
            return False
        if i == 0:
            tested0 = True
    return True if tested0 else None


def _assemble(cands, n, unit):
    """Try the candidate rows (pbt / pat variants) until the statement reconciles in every column."""
    keys = [k for k in KEYNAMES if cands.get(k)]
    if "revenue" not in keys or "pat" not in keys:
        return None
    base = {k: (cands[k][0][1][:3] + [None, None, None])[:3] for k in keys if k not in ("pbt", "pat")}
    for pb, pt in itertools.product(cands.get("pbt") or [None], cands.get("pat")):
        d = dict(base)
        d["pbt"] = ((pb[1][:3] + [None] * 3)[:3]) if pb else [None] * 3
        d["pat"] = (pt[1][:3] + [None] * 3)[:3]
        ok = _chk(d, unit)
        if ok:
            return d, True
    d = dict(base)
    d["pbt"] = ((cands["pbt"][0][1][:3] + [None] * 3)[:3]) if cands.get("pbt") else [None] * 3
    d["pat"] = (cands["pat"][0][1][:3] + [None] * 3)[:3]
    return d, False


def read_pdf(pdf_bytes, hint="", qhint=None):
    """-> (json, None) or (None, reason). qhint: BSE quarter code from the filing headline (used for the column dates when the header cannot be read)."""
    try:
        pages = _pdf_rows(pdf_bytes)
    except Exception as e:
        return None, f"rule: pdf open failed {repr(e)[:50]}"
    if not pages:
        return None, "rule: empty pdf"
    if len(re.sub(r"\W", "", "".join(t for t, _ in pages))) < 400:
        return None, "rule: no text layer"
    blocks = {"standalone": [], "consolidated": []}
    basis = None
    htxt, first_page_txt = "", ""
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
        for lb, nums, c in built:
            if (not nums or (len(nums) <= 2 and all(v is not None and 1990 <= abs(v) <= 2100 for v in nums))) and 3 < len(lb) < 170:
                l = lb.lower().strip()
                a, b = bool(re.search(r"\bstandalone\b", l)), bool(re.search(r"\bconsolidated\b", l))
                title = ("statement" in l or "financial result" in l or "results" in l) and "notes" not in l
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
    if not re.search(r"quarter|three months|3 months", low + " " + first_page_txt[:2500].lower()):
        return None, "rule: header has no quarter columns"
    unit = _unit(htxt) or _unit(" ".join(t[:2500] for t, _ in pages[:3]))
    if not unit:
        return None, "rule: unit not found"
    ds = _dates(htxt)
    if not (len(ds) >= 3 and _layout_ok(ds)):
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
    out = {"unit": unit, "quarter_end_columns": ds[:3], "consolidated": None, "standalone": None, "_rule": True, "_rule_ok": {}, "_printed": {}}
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
        r = _assemble(cands, n, unit)
        if r is None:
            why.append(f"{b[:4]}: missing {[k for k in ('revenue', 'pat') if not cands.get(k)]} n={n}")
            if b == "consolidated": return None, f"rule: consolidated table incomplete missing {[k for k in ('revenue', 'pat') if not cands.get(k)]} n={n}"
            continue
        d, ok = r
        rv_ = cands["revenue"][0][1]
        if ok and n >= 4 and None not in (rv_[0], rv_[3]) and rv_[0] > 0 and rv_[3] > 0:
            if rv_[0] > rv_[3] * 1.02:
                ok = False; why.append(f"{b[:4]}: first column larger than the year-to-date column")
            elif n >= 5 and ds[0].split(".")[1] == "09" and rv_[1] is not None and abs(rv_[3] - rv_[0] - rv_[1]) > 0.02 * rv_[3]:
                ok = False; why.append(f"{b[:4]}: half-year column is not quarter + previous quarter")
        if not ok:
            det = " ".join(f"{k}={d.get(k)}" for k in ("total_income", "total_expenses", "exceptional", "pbt", "tax", "associates", "pat", "depreciation", "finance_costs") if d.get(k))
            why.append(f"{b[:4]}: does not reconcile [{unit}] {det}")
            if b == "consolidated": return None, f"rule: consolidated table does not reconcile [{unit}] {det}"
            continue
        for k in KEYNAMES:
            d.setdefault(k, [None, None, None])
        e = d.pop("exceptional", None)
        d.pop("associates", None)
        out[b] = d
        out["_rule_ok"][b] = True
        out["_printed"][b] = 0
    if not out["consolidated"] and not out["standalone"]:
        return None, "rule: " + "; ".join(why or ["no results table recognised"])
    if not out["consolidated"]:
        alltxt = " ".join(t for t, _ in pages).lower()
        if re.search(r"statement of consolidated|consolidated (un)?audited financial results|consolidated financial results", alltxt):
            return None, "rule: filing mentions consolidated results but that table was not read"
    return out, None
