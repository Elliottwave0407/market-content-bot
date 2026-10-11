import json
import re
import time
from datetime import datetime

REV_KEYS = ["Net Sales/Revenue From Operations", "Net Sales", "Interest Earned/Net Income from sales/services"]
PBT_KEYS = ["Profit (+)/ Loss (-) from Ordinary Activities before Tax"]
PAT_STANDALONE = ["Net Profit"]
PAT_CONSOLIDATED = ["Net Profit after Mino Inter & Share of P & L", "Net Profit"]
EPS_KEYS = ["Basic EPS for continuing operation", "Basic EPS before Extraordinary items"]
MONTHS = {3: "Mar", 6: "Jun", 9: "Sep", 12: "Dec"}

def qcode(year, month):
    return 129 + ((year - 2026) * 12 + (month - 3)) // 3

def qlabel(code):
    n = int(round(code)) - 129
    months = n * 3 + 3
    year = 2026 + (months - 1) // 12
    month = (months - 1) % 12 + 1
    return f"{MONTHS[month]}-{str(year)[2:]}"

def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None

def first(d, keys):
    for k in keys:
        if k in d and num(d[k]) is not None:
            return num(d[k])
    return None

def _get(bse, path, params):
    r = bse.session.get(f"{bse.api_url}/{path}/w", params=params, timeout=30)
    try:
        return r.json()
    except Exception:
        return None

LOG = []

def complete(raw):
    has_rev = first(raw, REV_KEYS) is not None
    if not has_rev:
        return True
    return first(raw, EPS_KEYS) is not None and ("Expenditure" in raw or "Interest Earned/Net Income from sales/services" in raw)

def _tidy(k):
    return " ".join(str(k).split()) if k else k

def raw_standalone(bse, code, q):
    out = {}
    for attempt in range(3):
        d = _get(bse, "Corp_detailedResult_Transpose_ng", {"Scrip_cd": str(code), "Qtr": f"{q:.2f}"})
        out = {}
        for x in (d.get("table1", []) if isinstance(d, dict) else []):
            out.setdefault(_tidy(x.get("fld_desc")), x.get("Value"))
        if complete(out):
            break
        LOG.append(f"retry standalone {code} q{q} attempt {attempt + 1}")
        time.sleep(1)
    return out

def _cons_call(bse, code, name, q, rtype):
    d = _get(bse, "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng", {"type1": "c", "strtype": f"{q:.2f}", "strscripcd": str(code), "strscripname": name, "strresultType": rtype, "action": "show"})
    out = {}
    for x in (d if isinstance(d, list) else []):
        out.setdefault(_tidy(x.get("Description")), x.get("Amount"))
    return out

def raw_consolidated(bse, code, name, q):
    base = _cons_call(bse, code, name, q, "")
    if complete(base):
        return base
    for rtype in ("A", "U"):
        alt = _cons_call(bse, code, name, q, rtype)
        if not complete(alt):
            continue
        for k in ("Net Sales", "Interest Earned/Net Income from sales/services", "Net Profit", "Profit (+)/ Loss (-) from Ordinary Activities before Tax"):
            if k in base and k in alt and num(base[k]) != num(alt[k]):
                LOG.append(f"CONFLICT {code} q{q} mode {rtype} {k}: {base[k]} vs {alt[k]} -> not trusted")
                return base
        LOG.append(f"used mode {rtype} for consolidated {code} q{q}")
        return alt
    LOG.append(f"INCOMPLETE consolidated {code} q{q}")
    return base

def metrics(raw, basis):
    rev = first(raw, REV_KEYS)
    if rev is None:
        return None
    exp = first(raw, ["Expenditure"])
    dep = first(raw, ["Depreciation and amortisation expense"])
    fin = first(raw, ["Finance Costs"])
    bank = "Interest Earned/Net Income from sales/services" in raw
    ebitda = None
    if not bank and None not in (exp, dep, fin):
        ebitda = rev + exp - dep - fin
    pat = first(raw, PAT_STANDALONE if basis == "standalone" else PAT_CONSOLIDATED)
    return {"revenue": rev, "ebitda": ebitda, "pbt": first(raw, PBT_KEYS), "pat": pat, "eps": first(raw, EPS_KEYS), "bank": bank}

def fetch(bse, code, name, basis, q):
    raw = raw_standalone(bse, code, q) if basis == "standalone" else raw_consolidated(bse, code, name, q)
    return metrics(raw, basis)

def latest(bse, code, name, basis, start=131):
    for q in (start, start - 1, start - 2):
        m = fetch(bse, code, name, basis, q)
        if m:
            return q, m
    return None, None

def eps_pct(eps_a, eps_b, pat_a, pat_b):
    e = pct(eps_a, eps_b)
    p = pct(pat_a, pat_b)
    try:
        if abs(float(e[:-1]) - float(p[:-1])) > 5:
            return "NC"
    except Exception:
        pass
    return e

def pct(a, b):
    if a is None or b is None or b == 0:
        return "NA"
    if b < 0 or a < 0:
        return "NM"
    return f"{(a - b) / b * 100:+.1f}%"

def cr(v):
    return None if v is None else v / 10.0

QTR_WORDS = [
    (r"\bq1\b|first quarter|quarter ended 30\D{0,6}jun|30\.06|30/06|jun(e)?\s*30", 6),
    (r"\bq2\b|second quarter|half[\s-]*year|quarter ended 30\D{0,6}sep|30\.09|30/09|sep(tember)?\s*30", 9),
    (r"\bq3\b|third quarter|nine months|quarter ended 31\D{0,6}dec|31\.12|31/12|dec(ember)?\s*31", 12),
    (r"\bq4\b|fourth quarter|quarter ended 31\D{0,6}mar|31\.03|31/03|mar(ch)?\s*31|year ended 31\D{0,6}mar", 3),
]

def expected_quarter(text, filed):
    """Quarter code a filing refers to, from its headline; None if it cannot be determined."""
    t = (text or "").lower()
    months = {m for pat, m in QTR_WORDS if re.search(pat, t)}
    if len(months) != 1:
        return None
    m = months.pop()
    y = filed.year if datetime(filed.year, m, 28) <= filed else filed.year - 1
    return qcode(y, m)

def results(bse, code, name, basis, start=131, exact=None):
    if exact is not None:
        q, cur = exact, fetch(bse, code, name, basis, exact)
    else:
        q, cur = latest(bse, code, name, basis, start)
    if not cur:
        return None
    prev = fetch(bse, code, name, basis, q - 1)
    yago = fetch(bse, code, name, basis, q - 4)
    rows = []
    for key, label in [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pbt", "PBT"), ("pat", "Net profit"), ("eps", "EPS")]:
        c = cur.get(key)
        pv = prev.get(key) if prev else None
        yv = yago.get(key) if yago else None
        scale = (lambda v: v) if key == "eps" else cr
        if key == "eps":
            qoq = eps_pct(c, pv, cur.get("pat"), prev.get("pat") if prev else None)
            yoy = eps_pct(c, yv, cur.get("pat"), yago.get("pat") if yago else None)
        else:
            qoq, yoy = pct(c, pv), pct(c, yv)
        rows.append({"item": label, "cur": scale(c), "qoq": qoq, "yoy": yoy, "prev": scale(pv), "yago": scale(yv)})
    return {"code": code, "name": name, "basis": basis, "quarter": qlabel(q), "prev_q": qlabel(q - 1), "yago_q": qlabel(q - 4), "unit": "Rs Cr (EPS in Rs)", "rows": rows, "bank": cur["bank"]}

def fmt(v, eps=False):
    if v is None:
        return "NA"
    return f"{v:,.2f}" if (eps or abs(v) < 100) else f"{v:,.0f}"

def render(r):
    if not r:
        return "No reported results found"
    lines = [f"{r['name']} | {r['quarter']} | {r['basis']} | vs {r['prev_q']} (QoQ), {r['yago_q']} (YoY)"]
    for x in r["rows"]:
        if x["cur"] is None:
            continue
        e = x["item"] == "EPS"
        lines.append(f"  {x['item']}: {fmt(x['cur'], e)} | QoQ {x['qoq']} | YoY {x['yoy']}  (prev {fmt(x['prev'], e)}, yago {fmt(x['yago'], e)})")
    return "\n".join(lines)
