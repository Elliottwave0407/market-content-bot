"""Exchange-agnostic quarterly numbers: NSE integrated filings (2025+), NSE legacy results (pre-2025), BSE tables. Rs Cr."""
import re, json
from datetime import datetime

REF_I = {"Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing"}
REF_L = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}

def _val(t, tag):
    """value of a tag for the current-quarter context (OneD) else first occurrence"""
    best = None
    for m in re.finditer(r"<[A-Za-z0-9\-]+:%s\b([^>]*)>([^<]+)<" % tag, t):
        v = m.group(2).strip()
        if not re.match(r"^-?[0-9.]+$", v):
            continue
        if "OneD" in m.group(1):
            return float(v)
        if best is None:
            best = float(v)
    return best

def parse_xbrl(t):
    cr = lambda v: None if v is None else round(v / 1e7, 2)
    rev, oth = _val(t, "RevenueFromOperations"), _val(t, "OtherIncome") or 0
    pbt, fin, dep = _val(t, "ProfitBeforeTax"), _val(t, "FinanceCosts") or 0, _val(t, "DepreciationDepletionAndAmortisationExpense") or 0
    pat = _val(t, "ProfitLossForPeriod")
    if rev is None or pbt is None:
        return None
    eps = _val(t, "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations")
    return {"revenue": cr(rev), "ebitda": cr(pbt + fin + dep - oth), "pbt": cr(pbt), "pat": cr(pat), "eps": eps}

def _dt(s):
    for f in ("%d-%b-%Y", "%d-%B-%Y"):
        try: return datetime.strptime(s.title(), f)
        except Exception: pass
    return None

def _label(d): return d.strftime("%b-%y")

def nse_quarters(s, sym, want_n=9):
    """returns {qe_date: {basis, metrics, src}} preferring consolidated; latest revision wins"""
    out = {}
    def take(qe, basis, m, src, when):
        k = _dt(qe)
        if not k or not m: return
        cur = out.get(k)
        rank = (1 if basis == "consolidated" else 0, when or "")
        if cur is None or rank >= cur["rank"]:
            out[k] = dict(m, basis=basis, src=src, rank=rank)
    try:
        d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": "equities", "symbol": sym}, headers=REF_I, timeout=40).json().get("data", [])
    except Exception:
        d = []
    for x in d:
        if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"):
            continue
        try:
            t = s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        except Exception:
            continue
        basis = "consolidated" if x.get("consolidated") == "Consolidated" else "standalone"
        take(x.get("qe_Date"), basis, parse_xbrl(t), "nse-integrated", (x.get("creation_Date") or "")[:11])
    try:
        d = s.get("https://www.nseindia.com/api/corporates-financial-results", params={"index": "equities", "symbol": sym, "period": "Quarterly"}, headers=REF_L, timeout=40).json()
    except Exception:
        d = []
    for x in d:
        if not x.get("xbrl") or x.get("cumulative") not in (None, "Non-cumulative"):
            continue
        try:
            t = s.get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        except Exception:
            continue
        basis = "consolidated" if x.get("consolidated") == "Consolidated" else "standalone"
        take(x.get("toDate"), basis, parse_xbrl(t), "nse-legacy", (x.get("filingDate") or "")[:11])
    return out

def merged(s, sym, bse=None, code=None, name=""):
    """NSE first; BSE table fills quarters NSE lacks. Returns list oldest->newest of (label, metrics)."""
    q = nse_quarters(s, sym)
    if bse and code:
        import results_fetcher as rf
        for qc in range(131, 123, -1):
            try: lab = rf.qlabel(qc)
            except Exception: continue
            dt = _dt("30-" + lab) if False else None
            have = any(_label(k) == lab for k in q)
            if have: continue
            for basis in ("consolidated", "standalone"):
                try: m = rf.fetch(bse, code, name, basis, qc)
                except Exception: m = None
                if m and m.get("revenue") is not None:
                    k = datetime.strptime("01-" + lab, "%d-%b-%y")
                    q[k] = dict(m, basis=basis, src="bse", rank=(0, ""))
                    break
    rows = sorted(q.items())
    return [(_label(k), v) for k, v in rows]

def show(rows, p):
    prev = {}
    for lab, m in rows:
        rev, eb, pat = m.get("revenue"), m.get("ebitda"), m.get("pat")
        em = round(100 * eb / rev, 1) if rev and eb is not None else None
        p(f"{lab} {m['basis'][:4]} {m['src']} | rev {rev} | ebitda {eb} | ebitda% {em} | pat {pat} | eps {m.get('eps')}")
