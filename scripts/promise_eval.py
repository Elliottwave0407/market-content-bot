"""Code-only scoring of numeric promises against filed quarterly numbers (no LLM).
structure(): turns a promise's text into a spec {metric, low, high, by} where it can; evaluate(): compares with filed numbers.
Verdicts: delivered | delayed (reached within 2 quarters after 'by') | missed | open (not yet due / long-term not yet met) | None (not numeric -> LLM judge)."""
import re, sys, os, json
from datetime import datetime, date
sys.path.insert(0, os.path.dirname(__file__))
import store

MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
QE = [3, 6, 9, 12]

def qlabel(y, m): return datetime(y, m, 1).strftime("%b-%y")

def qend_on_or_after(d):
    for m in QE:
        if d.month <= m: return (d.year, m)
    return (d.year + 1, 3)

def add_q(yq, n):
    y, m = yq; i = QE.index(m) + n
    return (y + i // 4, QE[i % 4])

def parse_by(deadline, text, call):
    """-> (kind, value) kind: 'q' (y,m) | 'fy' year | None"""
    s = f"{deadline or ''} {text or ''}".lower()
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(?:of\s*)?'?(\d{2,4})", s)
    if m:
        y = int(m.group(2)); y = y + 2000 if y < 100 else y
        return "q", qend_on_or_after(date(y, MON[m.group(1)], 1))
    m = re.search(r"fy\s*'?(\d{2})", s)
    if m and "q" not in (deadline or "").lower().replace("fy", ""):
        return "fy", 2000 + int(m.group(1))
    m = re.search(r"q([1-4])\s*fy\s*'?(\d{2})", s)
    if m:
        fy = 2000 + int(m.group(2)); q = int(m.group(1)); return "q", ((fy - 1, 6), (fy - 1, 9), (fy - 1, 12), (fy, 3))[q - 1]
    if re.search(r"couple of months|next 2 months", s):
        mm = call.month + 2; y = call.year + (mm - 1) // 12; mm = (mm - 1) % 12 + 1
        return "q", qend_on_or_after(date(y, mm, 1))
    if re.search(r"next 12 months|12 months", s):
        return "q", qend_on_or_after(date(call.year + 1, call.month, 1))
    from datetime import timedelta
    ref = call - timedelta(days=45)                      # results calls come ~45 days after quarter end
    fyc = ref.year + (1 if ref.month > 3 else 0)         # fiscal year being reported
    if re.search(r"next year", s):
        return "fy", fyc + 1
    if re.search(r"couple of years|2 years|two years", s):
        return "fy", fyc + 2
    return None, None

def rng(text):
    t = text.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|x|crores?|cr)?\s*(?:to|-|–|and)\s*(\d+(?:\.\d+)?)", t)
    if m: return float(m.group(1)), float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:crores?|cr|%)?\s*plus\s*/?\s*minus", t) or re.search(r"close to\s*(\d+(?:\.\d+)?)", t)
    if m:
        v = float(m.group(1)); return v * 0.9, v * 1.1
    return None, None

def structure(pr, call_date):
    txt = pr.get("promise", ""); low_txt = txt.lower(); dl = pr.get("deadline")
    if re.search(r"ideal world|ideal capex", low_txt): return {"skip": "hypothetical"}
    lo, hi = rng(txt)
    kind, by = parse_by(dl, txt, call_date)
    if lo is None: return None
    if re.search(r"\bmrr\b|monthly run rate|run rate|exit mrr", low_txt):
        if hi > 200: return None
        return {"metric": "monthly_revenue", "low": lo, "high": hi, "by": (kind, by), "proxy": True, "tolerance": "+/-10% assumed for 'plus/minus' or 'close to'" if re.search(r"plus\s*/?\s*minus|close to", low_txt) and not re.search(r"\d\s*(?:to|-)\s*\d", low_txt) else None}
    if "ebitda" in low_txt and "%" in txt:
        if "plus/minus" in low_txt or "plus or minus" in low_txt:
            v = lo / 0.9; lo, hi = v - 5, v + 5
        return {"metric": "ebitda_margin", "low": lo, "high": hi, "by": (kind, by), "tolerance": "+/-5 pts assumed for 'plus/minus'" if hi - lo == 10 else None}
    if re.search(r"\bpat\b", low_txt) and "%" in txt:
        return {"metric": "pat_margin", "low": lo, "high": hi, "by": (kind, by)}
    if re.search(r"\d(\.\d+)?x", low_txt) and "revenue" in low_txt:
        return {"metric": "fy_revenue_x", "low": lo, "high": hi, "by": (kind, by), "base_fy": None}
    if pr.get("topic") == "revenue" and "%" in txt and re.search(r"grow", low_txt):
        return {"metric": "fy_cagr_pct", "low": lo, "high": hi, "by": (kind, by)}
    return None

def fy_of(yq): return yq[0] + (1 if yq[1] > 3 else 0)

def fy_rev(Q, fy):
    labs = [qlabel(fy - 1, 6), qlabel(fy - 1, 9), qlabel(fy - 1, 12), qlabel(fy, 3)]
    if all(l in Q for l in labs): return sum(Q[l]["revenue"] for l in labs)
    return None

def actual(Q, spec, yq):
    lab = qlabel(*yq); q = Q.get(lab)
    if not q: return None
    m = spec["metric"]
    if m == "monthly_revenue": return round(q["revenue"] / 3, 1)
    if m == "ebitda_margin" and q.get("revenue"): return round(100 * q["ebitda"] / q["revenue"], 1)
    if m == "pat_margin" and q.get("revenue"): return round(100 * q["pat"] / q["revenue"], 1)
    return None

def evaluate(Q, spec, call_date):
    """returns dict(verdict, detail) or None"""
    if spec.get("skip"): return {"verdict": "excluded", "detail": spec["skip"]}
    kind, by = spec["by"]; m = spec["metric"]
    latest = max(((int(l[-2:]) + 2000, MON[l[:3].lower()]) for l in Q))
    lo, hi = spec["low"], spec["high"]
    if m in ("fy_revenue_x", "fy_cagr_pct"):
        if kind != "fy": return None
        cur = fy_rev(Q, by)
        if cur is None: return {"verdict": "open", "detail": f"FY{by%100} not complete in filed data"}
        base_fy = spec.get("base_fy") or (by - (1 if m == "fy_revenue_x" else 2)); base = fy_rev(Q, base_fy)
        if base is None: return None
        if m == "fy_revenue_x":
            x = round(cur / base, 2); v = "delivered" if x >= lo else "missed"
            return {"verdict": v, "detail": f"FY{by%100} revenue {round(cur,1)} vs FY{base_fy%100} {round(base,1)} = {x}x (target {lo}-{hi}x)"}
        cagr = round(100 * ((cur / base) ** 0.5 - 1), 1); v = "delivered" if cagr >= lo else "missed"
        return {"verdict": v, "detail": f"FY{base_fy%100}->FY{by%100} CAGR {cagr}% (target {lo}-{hi}%)"}
    if kind == "fy": by = (by, 3); kind = "q"
    if kind is None:  # long term / undated: judge on latest 2 quarters
        a = [actual(Q, spec, add_q(latest, -k)) for k in (0, 1)]
        a = [x for x in a if x is not None]
        if not a: return None
        ok = all(x >= lo for x in a)
        return {"verdict": "open" if not ok else "delivered", "detail": f"undated/long-term; latest quarters {a} vs target {lo}-{hi}" + ("" if ok else " (not yet met)")}
    if by > latest: return {"verdict": "open", "detail": f"due {qlabel(*by)}, not yet filed"}
    a0 = actual(Q, spec, by)
    if a0 is None: return None
    if spec.get("proxy") and a0 < lo:
        return {"verdict": "inconclusive", "detail": f"{qlabel(*by)} quarterly-average monthly revenue {a0} < {lo}; exit run-rate is not in filings (needs call/judge evidence)", "value": a0}
    if a0 >= lo: return {"verdict": "delivered", "detail": f"{qlabel(*by)} {m} {a0} vs target {lo}-{hi}", "value": a0}
    for n in (1, 2):
        y2 = add_q(by, n)
        if y2 > latest: break
        a = actual(Q, spec, y2)
        if a is not None and a >= lo:
            return {"verdict": "delayed", "detail": f"{qlabel(*by)} {a0} < {lo}; reached {a} in {qlabel(*y2)} (+{n}q)", "value": a0}
    return {"verdict": "missed", "detail": f"{qlabel(*by)} {m} {a0} vs target {lo}-{hi}", "value": a0}

def run(sym):
    Q = store.load(sym, "quarters.json")["quarters"]
    db = store.load(sym, "promises.json")
    out = []
    for url, c in db["calls"].items():
        cd = datetime.strptime(c["filed"], "%d-%b-%Y").date()
        for x in c["promises"]:
            spec = structure(x, cd)
            if not spec: x.pop("code_check", None); continue
            r = evaluate(Q, spec, cd)
            if not r: x.pop("code_check", None); continue
            spec2 = dict(spec); spec2["by"] = list(spec["by"]) if spec.get("by") else None
            x["code_check"] = {"spec": spec2, **r, "basis": "filed quarterly numbers" + (" (quarterly average used as proxy for monthly run-rate)" if spec.get("proxy") else "")}
            out.append((c["filed"], x["promise"][:80], r["verdict"], r["detail"]))
    store.save(sym, "promises.json", db)
    return out

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "E2E"
    res = run(sym)
    for f, t, v, d in sorted(res, key=lambda r: datetime.strptime(r[0], "%d-%b-%Y")):
        print(f"{f} | {v.upper():9} | {t} | {d}")
    from collections import Counter
    print(Counter(r[2] for r in res))
