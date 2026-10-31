"""Quarterly results history, step 2: read the numbers from each listed NSE XBRL filing (no AI). Picks the current-quarter context (end date = filing's quarter end, 80-100 days), values in INR crore (EPS in INR). Resumable. Env DRY(1 = first MAXN filings, folder results_hist_dry), MAXN, BUDGET_MIN, WORKERS."""
import os, sys, re, json, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import store
DRY = (os.environ.get("DRY") or "1") == "1"; MAXN = int(os.environ.get("MAXN") or "0"); BUDGET = float(os.environ.get("BUDGET_MIN") or "150"); WORKERS = int(os.environ.get("WORKERS") or "4"); T0 = time.time()
SRC = os.path.join(store.ROOT, "results_hist", "filings.jsonl")
OUT = os.path.join(store.ROOT, "results_hist_dry" if DRY else "results_hist"); os.makedirs(OUT, exist_ok=True)
NUM = os.path.join(OUT, "numbers.jsonl")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
S = requests.Session()
def warm():
    try: S.get("https://www.nseindia.com/", headers=H, timeout=40)
    except Exception: pass
warm()
rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
rows = [r for r in rows if r.get("xbrl") and r["xbrl"] != "None"]
done = set(); 
if os.path.exists(NUM):
    for l in open(NUM, encoding="utf-8"):
        try: done.add(json.loads(l)["xbrl"])
        except Exception: pass
todo = [r for r in rows if r["xbrl"] not in done]
if MAXN: todo = todo[:MAXN]
p("filings", len(rows), "todo", len(todo), "dry" if DRY else "live")
TAGS = {"rev": ["RevenueFromOperations", "RevenueOnInvestments", "InterestEarned", "Income"], "oi": ["OtherIncome"], "inc": ["Income"], "exp": ["Expenses", "OperatingExpenses"], "emp": ["EmployeeBenefitExpense", "EmployeesCost"], "dep": ["DepreciationDepletionAndAmortisationExpense"], "fin": ["FinanceCosts"], "pbt": ["ProfitBeforeTax", "ProfitLossFromOrdinaryActivitiesBeforeTax"], "tax": ["TaxExpense"], "pat": ["ProfitLossForThePeriod", "ProfitLossForPeriod", "ProfitLossFromOrdinaryActivitiesAfterTax"], "eps": ["BasicEarningsPerShareAfterExtraordinaryItems", "BasicEarningsPerShareBeforeExtraordinaryItems"], "nii": ["NetInterestIncome"]}
def dt(s):
    try: return datetime.fromisoformat(s.strip()[:10])
    except Exception: return None
def parse(txt, to):
    ctx = {}
    for m in re.finditer(r"<(?:\w+:)?context\s+id=\"([^\"]+)\"(.*?)</(?:\w+:)?context>", txt, re.S):
        a = re.search(r"startDate>([^<]+)<", m.group(2)); b = re.search(r"endDate>([^<]+)<", m.group(2)); 
        if a and b and "<xbrldi:explicitMember" not in m.group(2): ctx[m.group(1)] = (dt(a.group(1)), dt(b.group(1)))
    qend = datetime.strptime(to.title(), "%d-%b-%Y"); best = None
    for cid, (s, e) in ctx.items():
        if s and e and e == qend and 75 <= (e - s).days <= 100: best = cid; break
    if not best:
        for cid, (s, e) in ctx.items():
            if s and e and e == qend and 150 <= (e - s).days <= 380: best = cid; break
    if not best: return None
    vals = {}
    for m in re.finditer(r"<(?:[\w\-]+:)([A-Za-z0-9_]+)\s[^>]*contextRef=\"([^\"]+)\"[^>]*>([^<]*)<", txt):
        t, c, v = m.groups()
        if c == best:
            try: vals.setdefault(t, float(v))
            except Exception: pass
    out = {"ctx_days": (ctx[best][1] - ctx[best][0]).days}
    for k, names in TAGS.items():
        for n in names:
            if n in vals:
                out[k] = round(vals[n] / (1 if k == "eps" else 1e7), 2); break
    if "rev" in out and out.get("rev") == out.get("inc") and "oi" in out and k != "eps": pass
    if all(x in out for x in ("pbt", "fin", "dep")) and "rev" in out: out["ebitda"] = round(out["pbt"] + out["fin"] + out["dep"] - out.get("oi", 0), 2)
    return out
def work(r):
    for a in range(3):
        try:
            resp = S.get(r["xbrl"], headers=H, timeout=60)
            if resp.status_code in (401, 403): warm(); time.sleep(2 * (a + 1)); continue
            if resp.status_code != 200: time.sleep(2 * (a + 1)); continue
            n = parse(resp.text, r["to"])
            return {**{k: r[k] for k in ("sym", "idx", "isin", "name", "to", "q", "cons", "audited", "filed", "xbrl")}, "n": n}
        except Exception: time.sleep(2 * (a + 1))
    return None
ok = bad = 0; buf = []
def flush():
    global buf
    with open(NUM, "a", encoding="utf-8") as fh:
        for x in buf: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    buf = []
with ThreadPoolExecutor(WORKERS) as ex:
    for i in range(0, len(todo), 200):
        if (time.time() - T0) / 60 > BUDGET: break
        for res in ex.map(work, todo[i:i + 200]):
            if res is None or not res["n"]: bad += 1
            else: ok += 1
            if res: buf.append(res)
        flush(); p("progress", i + 200, "ok", ok, "no-numbers/failed", bad, f"{(time.time()-T0)/60:.0f} min")
flush()
p("end: ok", ok, "bad", bad)
if DRY:
    for l in list(open(NUM, encoding="utf-8"))[:6]: p("  sample", l[:330].strip())
publish()
