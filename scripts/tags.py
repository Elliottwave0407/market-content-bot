"""Hashtag helpers. Company tag = NSE symbol (else BSE ticker) from state/symbols.json; if unknown, the cleaned full company name. Never guesses a ticker."""
import os, re, json

_SYMS = {}
_LOADED = [False]
_DROP = {"ltd", "limited", "pvt", "private", "inc", "corporation", "corp", "plc", "and", "the", "of"}

def _load():
    if _LOADED[0]:
        return
    _LOADED[0] = True
    try:
        _SYMS.update(json.load(open(os.path.join(os.path.dirname(__file__), "..", "state", "symbols.json"))).get("m", {}))
    except Exception:
        pass

def clean(s):
    return re.sub(r"[^A-Za-z0-9]", "", s or "")

def name_tag(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "") if w and w.lower() not in _DROP]
    words = [w if w.isupper() and len(w) <= 5 else w[:1].upper() + w[1:] for w in words][:4]
    t = "".join(words)
    return ("#" + t) if len(t) >= 3 else ""

def company_tag(code=None, name=None, symbol=None):
    _load()
    sym = clean(symbol) if symbol else clean(_SYMS.get(str(code), "")) if code is not None else ""
    if sym and not sym.isdigit() and len(sym) >= 2:
        return "#" + sym
    return name_tag(name)

def quarter_tag(qlabel):
    """'Sep-26' -> '#Q2FY27'"""
    from datetime import datetime
    try:
        d = datetime.strptime(qlabel, "%b-%y")
    except Exception:
        return ""
    qn = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    if not qn:
        return ""
    fy = d.year + 1 if d.month > 3 else d.year
    return f"#Q{qn}FY{str(fy)[2:]}"

def join(*tags):
    seen, out = set(), []
    for t in tags:
        if t and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return " ".join(out)
