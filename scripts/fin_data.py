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

# ---------------- balance sheet + cash flow (half-yearly integrated filings) ----------------
def _ctx(t, tag, ctx_pref):
    for m in re.finditer(r"<[A-Za-z0-9\-]+:%s\b([^>]*)>([^<]+)<" % tag, t):
        v = m.group(2).strip()
        if re.match(r"^-?[0-9.]+$", v) and re.search(r'contextRef="%s"' % ctx_pref, m.group(1)):
            return float(v)
    return None

def parse_balance(t):
    cr = lambda v: None if v is None else round(v / 1e7, 2)
    I = lambda tag: _ctx(t, tag, "OneI"); F = lambda tag: _ctx(t, tag, "FourD")
    if I("Assets") is None:
        return None
    return {"assets": cr(I("Assets")), "equity": cr(I("Equity")),
            "borrowings_noncurrent": cr(I("BorrowingsNoncurrent")), "borrowings_current": cr(I("BorrowingsCurrent")),
            "cash": cr(I("CashAndCashEquivalents")), "other_bank_balances": cr(I("BankBalanceOtherThanCashAndCashEquivalents")),
            "trade_receivables": cr(I("TradeReceivablesCurrent")), "trade_payables": cr(I("TradePayablesCurrent")),
            "inventories": cr(I("Inventories")), "ppe": cr(I("PropertyPlantAndEquipment")), "cwip": cr(I("CapitalWorkInProgress")),
            "cfo_ytd": cr(F("CashFlowsFromUsedInOperatingActivities")), "cfi_ytd": cr(F("CashFlowsFromUsedInInvestingActivities")),
            "cff_ytd": cr(F("CashFlowsFromUsedInFinancingActivities")), "capex_ytd": cr(F("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")),
            "borrowings_raised_ytd": cr(F("ProceedsFromBorrowingsClassifiedAsFinancingActivities")),
            "revenue_ytd": cr(F("RevenueFromOperations")), "other_income_ytd": cr(F("OtherIncome")), "pbt_ytd": cr(F("ProfitBeforeTax")),
            "finance_cost_ytd": cr(F("FinanceCosts")), "dep_ytd": cr(F("DepreciationDepletionAndAmortisationExpense"))}

def balance_sheets(s, sym):
    out = {}
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
        b = parse_balance(t)
        if not b:
            continue
        basis = "consolidated" if x.get("consolidated") == "Consolidated" else "standalone"
        k = x.get("qe_Date"); rank = (1 if basis == "consolidated" else 0, (x.get("creation_Date") or "")[:11])
        if k not in out or rank >= out[k]["_rank"]:
            out[k] = dict(b, basis=basis, _rank=rank, source=x.get("xbrl"))
    for v in out.values(): v.pop("_rank", None)
    return out
