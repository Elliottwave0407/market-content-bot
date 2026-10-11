import json

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

def raw_standalone(bse, code, q):
    d = _get(bse, "Corp_detailedResult_Transpose_ng", {"Scrip_cd": str(code), "Qtr": f"{q:.2f}"})
    out = {}
    for x in (d.get("table1", []) if isinstance(d, dict) else []):
        out.setdefault(x.get("fld_desc"), x.get("Value"))
    return out

def raw_consolidated(bse, code, name, q):
    d = _get(bse, "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng", {"type1": "c", "strtype": f"{q:.2f}", "strscripcd": str(code), "strscripname": name, "strresultType": "", "action": "show"})
    out = {}
    for x in (d if isinstance(d, list) else []):
        out.setdefault(x.get("Description"), x.get("Amount"))
    return out

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

def pct(a, b):
    if a is None or b is None or b == 0:
        return "NA"
    if b < 0 or a < 0:
        return "NM"
    return f"{(a - b) / b * 100:+.1f}%"

def cr(v):
    return None if v is None else v / 10.0

def results(bse, code, name, basis, start=131):
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
        rows.append({"item": label, "cur": scale(c), "qoq": pct(c, pv), "yoy": pct(c, yv), "prev": scale(pv), "yago": scale(yv)})
    return {"code": code, "name": name, "basis": basis, "quarter": qlabel(q), "prev_q": qlabel(q - 1), "yago_q": qlabel(q - 4), "unit": "Rs Cr (EPS in Rs)", "rows": rows, "bank": cur["bank"]}

def fmt(v, eps=False):
    if v is None:
        return "NA"
    return f"{v:,.2f}" if eps else f"{v:,.0f}"

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
