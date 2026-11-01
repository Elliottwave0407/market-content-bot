"""Quarterly results history for BSE (step 1): for every BSE scrip in the mcap list that is NOT already covered by NSE results (ISIN not in the NSE numbers), fetch standalone and consolidated figures for quarters Mar-24 .. Sep-26 through the same BSE endpoints the live results engine uses (results_fetcher.fetch). Resumable per code. Env: DRY, MAXN, BUDGET_MIN, WORKERS(5), ALL=1 (also dual-listed codes), QFROM(121), QTO(131)."""
import os, sys, json, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
from ci_out import p, publish
import store
import results_fetcher as rf
from bse import BSE
DRY = (os.environ.get("DRY") or "1") == "1"; MAXN = int(os.environ.get("MAXN") or "0"); BUDGET = float(os.environ.get("BUDGET_MIN") or "150"); W = int(os.environ.get("WORKERS") or "5"); ALL = os.environ.get("ALL") == "1"
QF = int(os.environ.get("QFROM") or "121"); QT = int(os.environ.get("QTO") or "131"); T0 = time.time()
OUT = os.path.join(store.ROOT, "results_bse_dry" if DRY else "results_bse"); os.makedirs(OUT, exist_ok=True)
DATA = os.path.join(OUT, "numbers.jsonl"); STATE = os.path.join(OUT, "_done.json")
mc = json.load(open(os.path.join(store.ROOT, "mcap", "mcap.json")))
nse_isin = set()
for d in ("results_hist", "results_if"):
    try:
        for l in open(os.path.join(store.ROOT, d, "filings.jsonl"), encoding="utf-8"):
            x = json.loads(l)
            if x.get("isin"): nse_isin.add(x["isin"])
    except Exception: pass
codes = [(v["s"], v.get("n") or "", isin) for isin, v in mc.items() if v.get("s")]
only = [c for c in codes if c[2] not in nse_isin]
p("BSE scrips in mcap", len(codes), "| ISIN in NSE results", len(codes) - len(only), "| BSE-only", len(only))
todo_all = codes if ALL else only
try: done = set(json.load(open(STATE)))
except Exception: done = set()
todo = [c for c in todo_all if c[0] not in done]
if MAXN: todo = todo[:MAXN]
p("todo", len(todo), "dry" if DRY else "live", "quarters", QF, "to", QT)
def one(c):
    code, name, isin = c; out = []
    try:
        with BSE(download_folder=tempfile.mkdtemp()) as b:
            for q in range(QT, QF - 1, -1):
                for basis in ("consolidated", "standalone"):
                    try: m = rf.fetch(b, code, name, basis, q)
                    except Exception as e: m = None
                    if m: out.append({"code": code, "name": name, "isin": isin, "q": rf.qlabel(q), "qcode": q, "basis": basis, **{k: m.get(k) for k in ("revenue", "ebitda", "pbt", "pat", "eps", "bank")}})
        return code, out, None
    except Exception as e:
        return code, [], type(e).__name__
n = nrows = errs = 0
with ThreadPoolExecutor(W) as ex, open(DATA, "a", encoding="utf-8") as fh:
    for i in range(0, len(todo), 40):
        if (time.time() - T0) / 60 > BUDGET: break
        for code, out, err in ex.map(one, todo[i:i + 40]):
            if err: errs += 1; continue
            for r in out: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            done.add(code); n += 1; nrows += len(out)
        fh.flush(); json.dump(sorted(done), open(STATE, "w"))
        p("progress", n, "codes", nrows, "rows", errs, "errors", f"{(time.time()-T0)/60:.0f} min")
json.dump(sorted(done), open(STATE, "w"))
p("end: codes", n, "rows", nrows, "errors", errs, "| done total", len(done), "of", len(todo_all))
publish()
