"""Rule-based reader for result PDFs: pulls the numbers straight out of the PDF's own text layer (no AI, no quota, ~0.3 s).
Returns the same JSON shape as gemini_read (unit, quarter_end_columns, consolidated, standalone) so every existing check (arithmetic, column dates, BSE-history cross-check,
size guard) still runs on it. Returns (None, reason) whenever the layout is not recognised: the caller then falls back to Gemini / NVIDIA.
Numbers are only ever copied from the PDF text, never computed or guessed, except the tax line which is summed from its printed current + deferred parts if no total line exists."""
import re

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
NUMRE = re.compile(r"^\(?[-−–]?\d[\d,]*(\.\d+)?\)?[*#^]?$")
NILS = {"-", "–", "—", "−", "--", "nil", "NIL", "Nil", "-.-"}
KEYS = ("revenue from operations", "total income", "profit before tax", "profit/(loss) before tax", "profit / (loss) before tax", "total expenses")


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
    """Words of a page grouped into visual rows (by vertical position), each row sorted left to right."""
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
    """-> (label text, [numbers or None...]) : numbers are the trailing run of numeric / nil tokens."""
    toks = [w[4] for w in row]
    i = len(toks)
    while i > 0 and (_isnum(toks[i - 1]) or toks[i - 1] in NILS):
        i -= 1
    nums = [(_num(t) if _isnum(t) else None) for t in toks[i:]]
    return " ".join(toks[:i]).strip(), nums


def clean_label(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(3):
        s2 = re.sub(r"^(\(?[a-z]{1,2}\)|\([ivx]{1,4}\)|[ivx]{1,4}\)|\d{1,2}\.|\d{1,2}\)|[-–•*]+)\s*", "", s)
        s2 = re.sub(r"^(add|less|plus)\s*[:\-]\s*", "", s2)
        if s2 == s:
            break
        s = s2
    return s.strip(" :")


def _date_strings(text):
    out = []
    t = text
    pats = [
        r"\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4}|\d{2})\b",
        r"\b(\d{1,2})(?:st|nd|rd|th)?[\s.,-]*(jan[a-z]*|feb[a-z]*|mar[a-z]*|apr[a-z]*|may|jun[a-z]*|jul[a-z]*|aug[a-z]*|sep[a-z]*|oct[a-z]*|nov[a-z]*|dec[a-z]*)[\s.,'-]*(\d{4}|\d{2})\b",
        r"\b(jan[a-z]*|feb[a-z]*|mar[a-z]*|apr[a-z]*|may|jun[a-z]*|jul[a-z]*|aug[a-z]*|sep[a-z]*|oct[a-z]*|nov[a-z]*|dec[a-z]*)[\s.]*(\d{1,2})(?:st|nd|rd|th)?[\s,]*(\d{4})\b",
    ]
    hits = []
    for pi, p in enumerate(pats):
        for m in re.finditer(p, t, re.I):
            try:
                g = m.groups()
                if pi == 0:
                    d, mo, y = int(g[0]), int(g[1]), int(g[2])
                elif pi == 1:
                    d, mo, y = int(g[0]), MONTHS[g[1][:3].lower()], int(g[2])
                else:
                    d, mo, y = int(g[1]), MONTHS[g[0][:3].lower()], int(g[2])
                if y < 100:
                    y += 2000
                if 1 <= d <= 31 and 1 <= mo <= 12 and 2000 <= y <= 2100:
                    hits.append((m.start(), f"{d:02d}.{mo:02d}.{y}"))
            except Exception:
                pass
    hits.sort()
    for _, s in hits:
        if s not in out:
            out.append(s)
    return out


def _unit(text):
    t = text.lower()
    m = re.search(r"(lakhs?|lacs?|lakh|crores?|\bcrs?\b|millions?|\bmn\b|thousands?|'000)", t)
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
        txt = pg.get_text("text")
        pages.append((txt, rows_of(pg)))
    return pages


PAT_REV = [r"^total revenue from operations", r"^revenue from operations", r"^total income from operations", r"^income from operations",
           r"^net sales/income from operations", r"^net sales", r"^sales/income from operations", r"^sales", r"^revenue from operation"]


def _first_match(rows, pats, start=0, need=3, avoid=()):
    for p in pats:
        for i in range(start, len(rows)):
            lb, nums, cands = rows[i]
            if len(nums) < need:
                continue
            for c in cands:
                if re.search(p, c) and not any(re.search(a, c) for a in avoid):
                    return i, nums
    return None, None


def _pick_rows(rows):
    """rows: [(label, nums, cands)] of one basis block -> dict key -> index of 3 numbers [c,p,y] (None for nil)."""
    got = {}
    def put(key, hit):
        i, nums = hit
        if i is not None and key not in got:
            got[key] = (i, nums)
    put("revenue", _first_match(rows, PAT_REV, need=3, avoid=("other operating", "segment")))
    put("total_income", _first_match(rows, [r"^total income\b(?! from operations)", r"^total revenue\b(?! from operations)"], need=3, avoid=("from operations", "segment")))
    put("other_income", _first_match(rows, [r"^other income"], need=3))
    put("total_expenses", _first_match(rows, [r"^total expenses", r"^total expenditure"], need=3))
    put("finance_costs", _first_match(rows, [r"^finance costs?", r"^interest and finance", r"^finance charges", r"^interest expenses?"], need=3))
    put("depreciation", _first_match(rows, [r"^depreciation", r"^amortisation|^amortization"], need=3))
    pb = _first_match(rows, [r"before tax", r"before income tax"], need=3, avoid=("exceptional", "extraordinary", "associate", "joint venture", "share of"))
    put("pbt", pb)
    start = pb[0] if pb[0] is not None else 0
    tx = _first_match(rows, [r"^total tax expenses?", r"^tax expenses?", r"^total income tax", r"^income tax expenses?", r"^total tax", r"^provision for (income )?tax", r"^tax$"], start=start, need=3,
                      avoid=("before", "deferred tax asset", "relating to"))
    if tx[0] is not None:
        put("tax", tx)
    else:       # sum printed parts under a "Tax expense" heading
        for i in range(start, len(rows)):
            lb, nums, cands = rows[i]
            if not nums and any(re.search(r"^tax expenses?|^income tax", c) for c in cands):
                parts = []
                for j in range(i + 1, min(i + 7, len(rows))):
                    l2, n2, c2 = rows[j]
                    if len(n2) >= 3 and any(re.search(r"current|deferred|earlier|prior|short|excess|mat\b", c) for c in c2):
                        parts.append(n2)
                    elif parts:
                        break
                if parts:
                    n = min(len(p) for p in parts)
                    got["tax"] = (i, [sum((p[k] or 0.0) for p in parts) for k in range(n)])
                break
    pi = got["pbt"][0] if "pbt" in got else 0
    pat = _first_match(rows, [r"^(net )?profit.{0,40}for the (period|quarter|year)", r"^(net )?(profit|loss).{0,30}for the (period|quarter|year)", r"^profit.{0,12}after tax", r"^(net )?profit.{0,30}after tax"],
                       start=pi + 1, need=3, avoid=("before", "attributable", "comprehensive", "discontinued", "owners", "non-controlling", "minority", "per share"))
    if pat[0] is None:
        pat = _first_match(rows, [r"^(net )?profit.{0,40}(continuing operations)"], start=pi + 1, need=3, avoid=("before", "attributable", "comprehensive", "discontinued", "owners"))
    put("pat", pat)
    pj = got["pat"][0] if "pat" in got else pi
    put("eps", _first_match(rows, [r"\bbasic\b", r"^earnings? per (equity )?share", r"^eps\b"], start=pj + 1, need=3, avoid=("diluted only",)))
    return got


def read_pdf(pdf_bytes, hint=""):
    """-> (json, None) or (None, reason)."""
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
    dates, unit = [], None
    seen_table = False
    for pno, (txt, rws) in enumerate(pages):
        low = txt.lower()
        if sum(k in low for k in KEYS) < 2:
            continue
        built = []
        for r in rws:
            lb, nums = split_row(r)
            cl = clean_label(lb)
            built.append([lb, nums, [cl]])
        for i in range(len(built)):     # wrapped labels: a label-only row above / below a number row belongs to it
            lb, nums, c = built[i]
            if nums and i > 0 and not built[i - 1][1]:
                c.append(clean_label(built[i - 1][0] + " " + lb))
            if nums and i + 1 < len(built) and not built[i + 1][1]:
                c.append(clean_label(lb + " " + built[i + 1][0]))
            if nums and not lb and i > 0 and not built[i - 1][1]:
                c.append(clean_label(built[i - 1][0]))
        page_basis = basis
        page_rows = []
        for i, (lb, nums, c) in enumerate(built):
            if not nums and 6 < len(lb) < 170:
                l = lb.lower()
                if ("statement" in l or "financial result" in l or "results" in l) and "notes" not in l:
                    a, b = bool(re.search(r"\bstandalone\b", l)), bool(re.search(r"\bconsolidated\b", l))
                    if a != b:
                        page_basis = "standalone" if a else "consolidated"
            if page_basis is None and not any(w in txt.lower()[:3000] for w in ("consolidated",)):
                pass
            page_rows.append((page_basis or "standalone", (lb, nums, c)))
        if basis is None and not any(b for b, _ in page_rows if False):
            pass
        for b, row in page_rows:
            blocks[b].append(row)
            basis = b
        if not seen_table:
            seen_table = True
            head = []
            for lb, nums, c in [x for _, x in page_rows]:
                if any(re.search(p, c[0]) for p in PAT_REV[:3]) and len(nums) >= 3:
                    break
                head.append(lb)
            htxt = " ".join(head)
            dates = _date_strings(htxt)
            unit = _unit(htxt) or _unit(txt[:2500]) or _unit(txt)
    if not unit:
        return None, "rule: unit not found"
    if not dates:
        dates = _date_strings(hint)[:1]
        if dates:
            d, mo, y = dates[0].split(".")
            mo, y = int(mo), int(y)
            def shift(mm, yy, k):
                t = yy * 12 + (mm - 1) - k
                return t // 12, t % 12 + 1
            (y1, m1), (y2, m2) = shift(mo, y, 3), shift(mo, y, 12)
            last = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
            dates = [dates[0], f"{last[m1]:02d}.{m1:02d}.{y1}", f"{last[m2]:02d}.{m2:02d}.{y2}"]
        else:
            return None, "rule: column dates not found"
    out = {"unit": unit, "quarter_end_columns": dates[:3], "consolidated": None, "standalone": None, "_rule": True}
    for b in ("consolidated", "standalone"):
        rows = blocks[b]
        if not rows:
            continue
        got = _pick_rows(rows)
        if "revenue" not in got or "pat" not in got:
            continue
        lens = {len(got[k][1]) for k in ("revenue", "pat") if k in got}
        if len(lens) != 1 or max(lens) > 9:
            continue
        d = {}
        for k in ("revenue", "other_income", "total_income", "total_expenses", "finance_costs", "depreciation", "pbt", "tax", "pat", "eps"):
            if k in got:
                n = got[k][1]
                d[k] = (n[:3] + [None, None, None])[:3]
            else:
                d[k] = [None, None, None]
        out[b] = d
    if not out["consolidated"] and not out["standalone"]:
        return None, "rule: no results table recognised"
    return out, None
