"""Quarterly results history, step 1: list every quarterly result filing per NSE symbol (equities + SME) from NSE, keep quarters ending on/after QFROM. Metadata only (xbrl link, quarter, audited, consolidated). Resumable. Env: DRY (1 = first MAXN symbols, writes to results_hist_dry), MAXN, BUDGET_MIN, QFROM (default 2024-03-31), WORKERS(1)."""
import os, sys, json, time, csv, io
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import store
DRY = (os.environ.get("DRY") or "1") == "1"; MAXN = int(os.environ.get("MAXN") or "0"); BUDGET = float(os.environ.get("BUDGET_MIN") or "150"); T0 = time.time()
QFROM = datetime.fromisoformat(os.environ.get("QFROM") or "2024-03-31")
OUT = os.path.join(store.ROOT, "results_hist_dry" if DRY else "results_hist"); os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
S = requests.Session()
def warm():
    try: S.get(H["Referer"], headers={**H, "Accept": "text/html"}, timeout=40)
    except Exception: pass
warm()
def symbols():
    out = []
    for idx, url in (("equities", "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"), ("sme", "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv")):
        try:
            r = S.get(url, headers=H, timeout=60); n0 = len(out)
            for row in csv.DictReader(io.StringIO(r.text)):
                row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if row.get("SYMBOL"): out.append((idx, row["SYMBOL"], row.get("ISIN NUMBER", "")))
            p("symbol list", idx, r.status_code, len(out) - n0)
        except Exception as e: p("symbol list failed", idx, type(e).__name__)
    return out
SYMS = symbols()
# add symbols seen in the concall coverage cache (covers any listing-file gaps)
try:
    seen = {s for _, s, _ in SYMS}
    for l in open(os.path.join(store.ROOT, "concall_coverage", "nse_filings.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        if r.get("symbol") and r["symbol"] not in seen: SYMS.append((r.get("idx", "equities"), r["symbol"], r.get("isin") or "")); seen.add(r["symbol"])
except Exception: pass
STATE = os.path.join(OUT, "_done.json"); DATA = os.path.join(OUT, "filings.jsonl")
try: done = json.load(open(STATE))
except Exception: done = {}
rows = []
if os.path.exists(DATA): rows = [json.loads(l) for l in open(DATA, encoding="utf-8") if l.strip()]
def pd(s):
    for f in ("%d-%b-%Y", "%d-%B-%Y"):
        try: return datetime.strptime(s.title() if s.isupper() else s, f)
        except Exception: pass
    return None
def fetch(idx, sym):
    for a in range(4):
        try:
            r = S.get(f"https://www.nseindia.com/api/corporates-financial-results?index={idx}&symbol={sym}&period=Quarterly", headers=H, timeout=50)
            if r.status_code in (401, 403): warm(); time.sleep(3 * (a + 1)); continue
            if r.status_code != 200: time.sleep(3 * (a + 1)); continue
            return r.json()
        except Exception: time.sleep(3 * (a + 1))
    return None
todo = [x for x in SYMS if x[1] not in done]
if MAXN: todo = todo[:MAXN]
p("symbols", len(SYMS), "todo", len(todo), "dry" if DRY else "live")
errs = 0; n = 0
for idx, sym, isin in todo:
    if (time.time() - T0) / 60 > BUDGET: break
    js = fetch(idx, sym)
    if js is None: errs += 1; continue
    kept = 0
    if not isinstance(js, list): js = js.get('data', []) if isinstance(js, dict) else []
    for x in js:
        if not isinstance(x, dict): continue
        td = pd(x.get("toDate") or "")
        if not td or td < QFROM: continue
        rows.append({"sym": sym, "idx": idx, "isin": x.get("isin") or isin, "name": x.get("companyName"), "from": x.get("fromDate"), "to": x.get("toDate"), "q": x.get("relatingTo"), "audited": x.get("audited") or x.get("resultDescription"), "cons": x.get("consolidated"), "filed": x.get("filingDate") or x.get("exchdisstime"), "xbrl": x.get("xbrl"), "ind": x.get("indAs")}); kept += 1
    done[sym] = kept; n += 1
    if n % 100 == 0:
        json.dump(done, open(STATE, "w")); open(DATA, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        p("progress", n, "symbols", len(rows), "filings", errs, "errors", f"{(time.time()-T0)/60:.0f} min")
    time.sleep(0.6)
json.dump(done, open(STATE, "w")); open(DATA, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
import collections
c = collections.Counter(r["to"] for r in rows)
p("end: symbols done", len(done), "of", len(SYMS), "| filings kept", len(rows), "| errors", errs, "| with xbrl", sum(1 for r in rows if r["xbrl"] and r["xbrl"] != "None"))
p("by quarter end", dict(sorted(c.items(), key=lambda kv: -kv[1])[:12]))
publish()
