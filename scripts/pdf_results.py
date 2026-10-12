"""Read a company's results PDF (text or scanned) into quarterly numbers. Pure PDF - no BSE needed."""
import os, re, subprocess, tempfile

NUMTOK = re.compile(r"^\(?-?[\d,]*\d(\.\d+)?\)?$")
DASHES = {"-", "–", "—", "--", "nil", "Nil", "NIL", "=", "_"}
UNIT_RE = re.compile(r"(lakhs?|lacs?|crores?|millions?|mn|thousands?)", re.I)
UNIT_MILLION = {"lakh": 0.1, "lac": 0.1, "crore": 10.0, "million": 1.0, "mn": 1.0, "thousand": 0.001}

def _unit_of(text):
    m = UNIT_RE.search(text)
    if not m:
        return None
    w = m.group(1).lower()
    for k, v in UNIT_MILLION.items():
        if w.startswith(k):
            return k, v
    return None

def _group_rows(words):
    """words: (x0,y0,x1,y1,text) -> list of rows (list of words sorted by x)."""
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows, cur, cy = [], [], None
    for w in words:
        yc, h = (w[1] + w[3]) / 2, max(w[3] - w[1], 1)
        if cur and abs(yc - cy) <= 0.6 * h:
            cur.append(w)
        else:
            if cur:
                rows.append(sorted(cur, key=lambda a: a[0]))
            cur, cy = [w], yc
    if cur:
        rows.append(sorted(cur, key=lambda a: a[0]))
    return rows

def extract_rows(content, ocr_max=8, max_pages=14):
    """Return (pages, ocr_pages, rows) rows = list of [token,...] in reading order."""
    import pymupdf
    doc = pymupdf.open(stream=content, filetype="pdf")
    out, ocrp = [], 0
    for i, pg in enumerate(doc):
        if i >= max_pages:
            break
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in pg.get_text("words")]
        if sum(len(w[4]) for w in words) < 400 and ocrp < ocr_max:
            try:
                pix = pg.get_pixmap(dpi=200)
                with tempfile.TemporaryDirectory() as td:
                    f = os.path.join(td, "p.png")
                    pix.save(f)
                    tsv = subprocess.run(["tesseract", f, "stdout", "--psm", "6", "tsv"], capture_output=True, text=True, timeout=120).stdout
                ow = []
                for line in tsv.splitlines()[1:]:
                    c = line.split("\t")
                    if len(c) >= 12 and c[11].strip() and float(c[10]) >= 0:
                        x, y, w_, h_ = int(c[6]), int(c[7]), int(c[8]), int(c[9])
                        ow.append((x, y, x + w_, y + h_, c[11].strip()))
                words = words + ow
                ocrp += 1
            except Exception:
                pass
        for r in _group_rows(words):
            out.append([w[4] for w in r])
        out.append(["<<PAGE>>"])
    return len(doc), ocrp, out

def _fix(tok):
    """Repair common text-layer glitches: '149,77' -> '149.77'; '1.710.72' -> '1,710.72'."""
    if re.match(r"^\(?-?\d{1,3}(,\d{2,3})*,\d{2}\)?$", tok) and not re.match(r"^\(?-?\d{1,3}(,\d{2})+,\d{3}\)?$", tok):
        m = re.match(r"^(\(?-?)([\d,]+),(\d{2})(\)?)$", tok)
        if m and (len(m.group(2).split(",")[-1]) in (1, 2, 3)) and "," in tok and tok.count(",") >= 1:
            # decimal comma only if the last group has exactly 2 digits AND the token is not valid Indian/western grouping
            if not re.match(r"^\(?-?\d{1,3}(,\d{3})*\)?$", tok) and not re.match(r"^\(?-?\d{1,2}(,\d{2})*,\d{3}\)?$", tok):
                return m.group(1) + m.group(2) + "." + m.group(3) + m.group(4)
    if re.match(r"^\(?-?\d{1,3}(\.\d{3})+\.\d{2}\)?$", tok):
        m = re.match(r"^(\(?-?)([\d.]+)\.(\d{2})(\)?)$", tok)
        return m.group(1) + m.group(2).replace(".", ",") + "." + m.group(3) + m.group(4)
    return tok

def _merge(row):
    out, i = [], 0
    while i < len(row):
        t = row[i]
        if i + 1 < len(row) and re.match(r"^\(?-?[\d,]*\d[,.]$", t) and re.match(r"^[\d,]*\d(\.\d+)?\)?$", row[i + 1].lstrip("(")):
            out.append(t + row[i + 1]); i += 2; continue
        if t in ("(", "(-") and i + 1 < len(row) and re.match(r"^[\d,]*\d(\.\d+)?\)?$", row[i + 1]):
            out.append("(" + row[i + 1]); i += 2; continue
        out.append(t); i += 1
    return [_fix(x) for x in out]

def _num(tok):
    if tok in DASHES:
        return 0.0, 0
    if not NUMTOK.match(tok):
        return None
    if tok.startswith("(") != tok.endswith(")"):
        return None
    neg = tok.startswith("(") or tok.startswith("-")
    s = tok.strip("()-").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return (-v if neg else v), (len(s.split(".")[1]) if "." in s else 0)

def _split(row):
    """-> (label, [(value,decs),...]); numbers = trailing numeric tokens after last alphabetic token."""
    row = _merge(row)
    last_alpha = -1
    for i, t in enumerate(row):
        if _num(t) is None:
            last_alpha = i
    label = " ".join(row[:last_alpha + 1])
    nums = []
    for t in row[last_alpha + 1:]:
        n = _num(t)
        if n is not None:
            nums.append(n)
    return label, nums

def _field(label):
    l = re.sub(r"[^a-z ]+", " ", label.lower())
    l = re.sub(r"\s+", " ", l).strip()
    if "other income" in l and "total" not in l:
        return "oi"
    if re.search(r"total (net )?(revenue|income) from operations?|total operating (revenue|income)", l):
        return "rev_total"
    if re.search(r"(revenue|income|sales) from operations?|net sales|^sales", l) and "other" not in l:
        return "rev"
    if re.search(r"total income|total revenue", l):
        return "ti"
    if "total expenses" in l or re.search(r"total expenditure", l):
        return "exp"
    if "before" in l and "tax" in l:
        if "exceptional" in l and "after" not in l:
            return "pbt_pre"
        return "pbt"
    if re.search(r"total tax|tax expense", l) and "before" not in l:
        return "tax"
    if re.search(r"(net )?(profit|loss).*(for the|after tax)|profit after tax|^net profit", l) and not re.search(r"before|attributable|comprehensive|owners|non controlling|minority|other|discontinued|associate|joint venture|share of|tax expense", l):
        return "pat"
    if l.startswith("basic") or re.search(r"basic.*(eps|per share)|earnings per share.*basic", l):
        return "eps"
    return None

def parse(rows):
    """-> list of tables: {basis, unit, vals{field:[(v,decs)x<=3]}}. Side-by-side standalone|consolidated tables are split."""
    tables, curs, basis, unit = [], None, None, None
    recent, ridx, bidx = [], 0, -999
    for r in rows:
        if r == ["<<PAGE>>"]:
            continue
        ridx += 1
        text = " ".join(r)
        low = text.lower()
        recent.append(low)
        recent = recent[-14:]
        u = _unit_of(text) if (len(r) <= 12 and re.search(r"rs|₹|inr|in (lakh|lac|crore|million|mn|thousand)|amount|figures", low)) else None
        if u:
            unit = u
        if re.search(r"consolidated (unaudited |audited )?(financial )?results|statement of (unaudited |audited )?consolidated|consolidated unaudited|consolidated financial results", low):
            basis, bidx = "consolidated", ridx
        elif re.search(r"standalone (unaudited |audited )?(financial )?results|statement of (unaudited |audited )?standalone|standalone unaudited|standalone financial results", low):
            basis, bidx = "standalone", ridx
        label, nums = _split(r)
        f = _field(label) if nums else None
        if f in ("rev", "rev_total") and (curs is None or ("rev" in curs[0]["vals"] and f == "rev" and curs[0]["rowcount"] > 25)):
            hdr = " ".join(recent)
            ps, pc = hdr.find("standalone"), hdr.find("consolidated")
            n = len(nums)
            if ps >= 0 and pc >= 0 and n >= 6 and n % 2 == 0:
                order = ["standalone", "consolidated"] if ps < pc else ["consolidated", "standalone"]
                curs = [{"basis": order[0], "unit": unit, "vals": {}, "rowcount": 0, "split": True},
                        {"basis": order[1], "unit": unit, "vals": {}, "rowcount": 0, "split": True}]
            else:
                curs = [{"basis": basis if ridx - bidx <= 25 else None, "unit": unit, "vals": {}, "rowcount": 0, "split": False}]
            tables.extend(curs)
        if curs is not None:
            for c in curs:
                c["rowcount"] += 1
                if c["unit"] is None and unit:
                    c["unit"] = unit
            if f and nums:
                n = len(nums)
                if curs[0]["split"] and n >= 6 and n % 2 == 0:
                    parts = [nums[: n // 2][:3], nums[n // 2:][:3]]
                    for c, part in zip(curs, parts):
                        if f == "rev_total":
                            c["vals"]["rev"] = part
                        elif f not in c["vals"]:
                            c["vals"][f] = part
                else:
                    c = curs[0]
                    if f == "rev_total":
                        c["vals"]["rev"] = nums[:3]
                    elif f not in c["vals"]:
                        c["vals"][f] = nums[:3]
    tables = [t for t in tables if "rev" in t["vals"]]
    unk = [t for t in tables if t["basis"] is None]
    if unk:
        known = {t["basis"] for t in tables if t["basis"]}
        if len(tables) == 2 and not known:
            tables[0]["basis"], tables[1]["basis"] = "standalone", "consolidated"
            tables[0]["guess"] = tables[1]["guess"] = True
        elif len(tables) == 2 and len(known) == 1:
            other = "standalone" if "consolidated" in known else "consolidated"
            for t in unk:
                t["basis"], t["guess"] = other, True
    return tables

def checks(t):
    """Arithmetic checks on the current-quarter column. -> dict of bool/None"""
    v = {k: x[0][0] for k, x in t["vals"].items() if x}
    def ok(a, b):
        return abs(a - b) <= max(0.02 * 1, 0.002 * max(abs(a), abs(b)), 1.5)
    out = {}
    if "ti" in v and "exp" in v and ("pbt_pre" in v or "pbt" in v):
        out["ti_exp_pbt"] = ok(v["ti"] - v["exp"], v.get("pbt_pre", v.get("pbt")))
    if "pbt" in v and "tax" in v and "pat" in v:
        out["pbt_tax_pat"] = ok(v["pbt"] - v["tax"], v["pat"])
    return out
