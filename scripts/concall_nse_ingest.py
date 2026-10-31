"""Read the transcripts the BSE feed missed (found by concall_coverage.py): NSE transcript filings of NSE-only companies, BSE-listed companies whose transcript never reached the store, and stored records that were skipped.
Each is downloaded from its NSE archive link, read with the current reader (SCHEMA_V, MODELS from env) and verified, and stored in the same format as the BSE reads.
Key: <bse code>|<day> when the company has a BSE code, else NSE:<symbol>|<day>. Skips a filing if the same company already has a real (non-skipped) record within +-DUP_DAYS days (probably the same call filed on both exchanges).
Env: STATUSES (default all three), DUP_DAYS (default 21), MAXN, BUDGET_MIN, WORKERS, DRY (1 = writes only to OUT_DIR). Posts nothing."""
import os, sys, re, io, json, time, glob, threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, wait
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import concall_extract as CE
ROOT = CE.store.ROOT
DRY = os.environ.get("DRY", "") == "1"
STATUSES = set((os.environ.get("STATUSES") or "nse_only,bse_listed_missing,covered_but_skipped").split(","))
DUP = int(os.environ.get("DUP_DAYS") or "21")
MINW = int(os.environ.get("MIN_WORDS") or "1000")
LOG = os.path.join(ROOT, "concall_coverage", "_ingest_log.jsonl"); STATE = os.path.join(ROOT, "concall_coverage", "_ingest_state.json")
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.nseindia.com/"}

def pdf_text(url):
    from pypdf import PdfReader
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HDR, timeout=60)
            if r.status_code != 200 or len(r.content) < 2000 or len(r.content) > 15_000_000: time.sleep(3); continue
            rd = PdfReader(io.BytesIO(r.content))
            return " ".join((pg.extract_text() or "") for pg in rd.pages)
        except Exception: time.sleep(3)
    return None

def read(m):
    t0 = time.time()
    txt = pdf_text(m["url"])
    if not txt: return {"fail": "no_download_or_text"}
    t = CE.prep(txt)
    if len(t.split()) < MINW: return {"skip": "short_or_scanned", "words": len(t.split())}
    raw, used, bad = [], None, 0; chs = CE.chunks(t)
    for ch in chs:
        got = None
        if (time.time() - t0) / 60 > 12: bad += 1; continue
        for mod in CE.MODELS:
            got = CE.call(mod, ch)
            if got is not None: used = used or mod.split("/")[-1]; break
        if got is None: bad += 1; continue
        raw += got.get("items") or []
    if bad == len(chs): return None
    ok = CE.verify(raw, t)
    return {"words": len(t.split()), "model": used, "n_raw": len(raw), "n_ok": len(ok), "items": ok}

def main():
    if not CE.NV and not CE.MK: p("no model key"); return
    miss = [json.loads(l) for l in open(os.path.join(ROOT, "concall_coverage", "missing.jsonl"), encoding="utf-8")]
    miss = [x for x in miss if x["status"] in STATUSES]
    done = CE.load_done()
    try: attempted = set(json.load(open(os.path.join(ROOT, "concall_coverage", "_ingest_done.json"))))
    except Exception: attempted = set()
    allrec = {}
    for f in glob.glob(os.path.join(ROOT, "concall_facts", "20*.jsonl")):
        for l in open(f, encoding="utf-8"):
            try: r = json.loads(l)
            except Exception: continue
            if not r.get("skip"): allrec.setdefault(str(r["code"]), []).append(r["day"])
    def dup(code, day):
        dd = datetime.fromisoformat(day)
        return any(abs((datetime.fromisoformat(d) - dd).days) <= DUP for d in allrec.get(code, []))
    todo, ndup = [], 0
    for x in sorted(miss, key=lambda x: x["day"], reverse=True):
        code = x.get("bse_code") or ("NSE:" + (x["symbol"] or ""))
        key = f"{code}|{x['day']}"
        if key in done or key in attempted: continue
        if x.get("bse_code") and dup(code, x["day"]) : ndup += 1; attempted.add(key); continue
        todo.append({**x, "key": key, "code": code})
    p("models:", ", ".join(m.split("/")[-1] for m in CE.MODELS), "| schema", CE.SCHEMA_V, "| dry" if DRY else "| live", "| to read", len(todo), "| dup-skipped", ndup, "| statuses", sorted(STATUSES))
    stats = {"read": 0, "skipped_short": 0, "failed": 0}; progressed = 0
    def out_of_time(): return (time.time() - CE.T0) / 60 > CE.BUDGET_MIN or (CE.MAXN and progressed >= CE.MAXN)
    i = 0
    while i < len(todo) and not out_of_time():
        batch = min(CE.WORKERS * 2, (CE.MAXN - progressed) if CE.MAXN else 10 ** 6)
        if batch <= 0: break
        part = todo[i:i + batch]; i += batch
        ex = ThreadPoolExecutor(CE.WORKERS)
        try:
            futs = {ex.submit(read, m): m for m in part}
            wait(list(futs), timeout=40 * 60)
            for f, m in futs.items():
                if not f.done(): stats["failed"] += 1; continue
                try: r = f.result()
                except Exception: r = None
                if r is None or r.get("fail"):
                    stats["failed"] += 1
                    if r and r.get("fail"): attempted.add(m["key"])
                    continue
                attempted.add(m["key"]); progressed += 1
                base = {"key": m["key"], "code": m["code"], "name": m.get("name"), "day": m["day"], "v": CE.SCHEMA_V, "src": m["url"], "exch": "NSE", "symbol": m.get("symbol"), "cov": m["status"]}
                if r.get("skip"): stats["skipped_short"] += 1; done[m["key"]] = {**base, "skip": r["skip"], "words": r["words"]}
                else:
                    stats["read"] += 1; done[m["key"]] = {**base, "words": r["words"], "model": r["model"], "n_raw": r["n_raw"], "n_ok": r["n_ok"], "items": r["items"], "at": datetime.now(CE.IST).strftime("%Y-%m-%d %H:%M")}
                with open(LOG, "a") as lf: lf.write(json.dumps({"t": datetime.now(CE.IST).strftime("%m-%d %H:%M"), "key": m["key"], "st": m["status"], "res": "skip" if r.get("skip") else "read", "n": r.get("n_ok"), "dry": DRY}) + "\n")
        finally: ex.shutdown(wait=False, cancel_futures=True)
        CE.save(done)
        if not DRY: json.dump(sorted(attempted), open(os.path.join(ROOT, "concall_coverage", "_ingest_done.json"), "w"))
        p("progress", progressed, stats, f"{(time.time() - CE.T0) / 60:.0f} min")
    left = len([1 for x in todo[i:]])
    if not DRY: json.dump(sorted(attempted), open(os.path.join(ROOT, "concall_coverage", "_ingest_done.json"), "w"))
    json.dump({"remaining": left, "progressed": progressed, "stats": stats, "dry": DRY}, open(STATE if not DRY else STATE.replace(".json", "_dry.json"), "w"))
    p("end:", stats, "remaining", left)

if __name__ == "__main__":
    try: main()
    finally:
        publish(); sys.stdout.flush(); os._exit(0)
