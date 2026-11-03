"""Backup source for result numbers: NSE's own structured (XBRL) filing data, used only when BSE has no numbers yet.
Switched on with env NSE_BACKUP=1 (default off). Returns None whenever it is not fully sure; the caller then behaves exactly as before.
Units: returned metrics are in Rs million (same as the BSE table the card code expects); NSE's parse is Rs Cr, so x10."""
import os, json, time, calendar
import fin_data as fd
import nse_results as nr

ON = os.environ.get("NSE_BACKUP", "0") == "1"
MILLION = ("revenue", "ebitda", "pbt", "pat", "fin", "oth")
_SYM = {}
_CACHE = {}      # (code, label) -> (time, result)
NEG_TTL, POS_TTL = 120, 6 * 3600
_MON = {m: i for i, m in enumerate(["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

def _qends(label, n=6):
    mon, yy = label.split("-")
    m, y = _MON[mon], 2000 + int(yy)
    out = []
    for _ in range(n):
        out.append((f"{calendar.monthrange(y, m)[1]:02d}-{mon_name(m)}-{y}".lower(), f"{mon_name(m)}-{str(y)[2:]}"))
        m -= 3
        if m <= 0: m += 12; y -= 1
    return out

def mon_name(m): return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m]

def _rows(sym):
    s = nr.sess()
    for idx in ("equities", "sme"):
        for _ in range(2):
            try:
                r = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=30)
                if r.status_code == 200 and r.text.strip():
                    d = r.json().get("data", [])
                    if d: return d
                    break
                nr._S["sess"] = None; s = nr.sess()
            except Exception:
                nr._S["sess"] = None; time.sleep(1); s = nr.sess()
    return []

def get(code, label, cons_expected=False):
    """-> {'basis', 'quarters': [5 x {'q','m'}], 'yprev': m|None} for the quarter `label` (e.g. 'Sep-26'), or None."""
    if not ON: return None
    key = (str(code), label)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < (POS_TTL if hit[1] else NEG_TTL): return hit[1]
    res = None
    try: res = _get(str(code), label, cons_expected)
    except Exception: res = None
    _CACHE[key] = (time.time(), res)
    return res

def _get(code, label, cons_expected):
    if not _SYM:
        _SYM.update(json.load(open("state/symbols.json")).get("m", {}))
    sym = _SYM.get(code)
    if not sym: return None
    d = _rows(sym)
    if not d: return None
    ends = _qends(label)
    def pick(qe, basis):
        best = None
        for x in d:
            if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"): continue
            if not str(x.get("qe_Date") or "").lower().startswith(qe): continue
            if ("consolidated" if x.get("consolidated") == "Consolidated" else "standalone") != basis: continue
            if best is None or (x.get("creation_Date") or "") >= (best.get("creation_Date") or ""): best = x
        return best
    basis = "consolidated" if pick(ends[0][0], "consolidated") else ("standalone" if pick(ends[0][0], "standalone") else None)
    if basis is None: return None
    if basis == "standalone" and cons_expected: return None     # standing rule: never standalone while a consolidated result may exist
    ms = []
    for qe, lab in ends:
        x = pick(qe, basis); m = None
        if x:
            try: m = fd.parse_xbrl(nr.sess().get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=45).text)
            except Exception: m = None
        if m: m = {k: (round(v * 10, 2) if k in MILLION and isinstance(v, (int, float)) else v) for k, v in m.items()}
        ms.append(m)
        time.sleep(0.3)
    if not ms[0] or ms[0].get("revenue") is None or ms[0].get("pat") is None: return None
    empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
    quarters = [{"q": lab, "m": ms[i] or dict(empty)} for i, (qe, lab) in enumerate(ends[:5])]
    return {"basis": basis, "quarters": quarters, "yprev": ms[5]}
