"""Re-read old schema-v1 concall transcripts with the v2 reader (prompt, verification, realignment) and replace their facts only when the new read is at least as good.
Order: companies above Rs 5,000 Cr first, then the rest, newest first. Resumable: handled keys are in store/concall_reread/_done.json; actions in store/concall_reread/log.jsonl.
Env: DRY=1 (read and log, change nothing in concall_facts), MAXN, BUDGET_MIN, WORKERS, MODELS (same as concall_extract). Posts nothing anywhere."""
import os, sys, re, json, time, glob, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concall_extract as CE
from ci_out import p, publish
RD = os.path.join(CE.store.ROOT, "concall_reread"); os.makedirs(RD, exist_ok=True)
DONE_F = os.path.join(RD, "_done_dry.json" if os.environ.get("DRY", "") == "1" else "_done.json"); LOG_F = os.path.join(RD, "log.jsonl"); STATE_F = os.path.join(RD, "_state.json")
DRY = os.environ.get("DRY", "") == "1"
BIG = float(os.environ.get("BIG_MCAP", "5000"))
LOCK = threading.Lock()

PER_DOC_MIN = float(os.environ.get("PER_DOC_MIN", "10"))
SHORT_MIN = int(os.environ.get("SHORT_MIN", "1000"))   # previously-skipped short transcripts (SHORT_MIN..1499 words) are read first
def reread(r):
    t0 = time.time()
    t = CE.prep(CE.CT.pdf_text(r["src"]) or "")
    if len(t.split()) < (SHORT_MIN if r.get("skip") else 1500): return {"fail": "no_text"}
    raw, used, bad = [], None, 0
    chs = CE.chunks(t)
    for ch in chs:
        got = None
        if (time.time() - t0) / 60 > PER_DOC_MIN: bad += 1; continue
        for m in CE.MODELS:
            if (time.time() - t0) / 60 > PER_DOC_MIN: break
            got = CE.call(m, ch)
            if got is not None:
                used = used or m.split("/")[-1]; break
        if got is None: bad += 1; continue
        raw += got.get("items") or []
    if bad == len(chs): return None
    ok = CE.verify(raw, t)
    return {"words": len(t.split()), "model": used, "n_raw": len(raw), "n_ok": len(ok), "items": ok}

def better(old, new):
    n_old = old.get("n_ok", len(old.get("items") or [])); n_new = new["n_ok"]
    return n_new >= max(4, int(0.6 * n_old))

def main():
    if not CE.NV and not CE.MK: p("no model key"); return
    done = CE.load_done()
    try: handled = set(json.load(open(DONE_F)))
    except Exception: handled = set()
    mc = json.load(open(os.path.join(CE.store.ROOT, "mcap", "mcap.json"))); cap = {v["s"]: v.get("m") or 0 for v in mc.values() if v.get("s")}
    todo = [r for r in done.values() if r.get("v") == 1 and not r.get("skip") and r["key"] not in handled]
    short = [r for r in done.values() if r.get("skip") == "short_or_scanned" and SHORT_MIN <= r.get("words", 0) < 1500 and r["key"] not in handled]
    todo.sort(key=lambda r: (0 if cap.get(r["code"], 0) >= BIG else 1, "".join(chr(255 - ord(c)) for c in r["day"])))
    todo = short + todo
    p("short skipped docs to try:", len(short))
    p("models:", ", ".join(m.split("/")[-1] for m in CE.MODELS), "| dry" if DRY else "| live", "| v1 left", len(todo), "| above", BIG, "Cr:", sum(1 for r in todo if cap.get(r["code"], 0) >= BIG))
    stats = {"replaced": 0, "kept_old": 0, "failed": 0}; progressed = 0
    def out_of_time(): return (time.time() - CE.T0) / 60 > CE.BUDGET_MIN or (CE.MAXN and progressed >= CE.MAXN)
    i = 0
    while i < len(todo) and not out_of_time():
        batch = min(CE.WORKERS * 2, (CE.MAXN - progressed) if CE.MAXN else 10 ** 6)
        if batch <= 0: break
        part = todo[i:i + batch]; i += batch
        ex = ThreadPoolExecutor(CE.WORKERS)
        try:
            futs = {ex.submit(reread, r): r for r in part}
            from concurrent.futures import wait as _wait
            _wait(list(futs), timeout=(PER_DOC_MIN * 3 + 5) * 60)
            for f in list(futs):
                r = futs[f]
                if not f.done(): stats["failed"] += 1; continue
                try: new = f.result()
                except Exception: new = None
                if not new or new.get("fail"):
                    stats["failed"] += 1
                    if new and new.get("fail"): handled.add(r["key"])
                    continue
                acc = better(r, new); progressed += 1
                with LOCK:
                    handled.add(r["key"])
                    with open(LOG_F, "a") as lf:
                        lf.write(json.dumps({"t": datetime.now(CE.IST).strftime("%m-%d %H:%M"), "key": r["key"], "act": "replace" if acc else "keep", "old": r.get("n_ok"), "new": new["n_ok"], "m": new["model"], "dry": DRY}) + "\n")
                    if acc:
                        stats["replaced"] += 1
                        if not DRY:
                            done[r["key"]] = {**{k: r[k] for k in ("key", "code", "name", "day", "src")}, "v": CE.SCHEMA_V, "words": new["words"], "model": new["model"], "n_raw": new["n_raw"], "n_ok": new["n_ok"], "items": new["items"], "at": datetime.now(CE.IST).strftime("%Y-%m-%d %H:%M"), "reread": True}
                    else: stats["kept_old"] += 1
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        if not DRY: CE.save(done)
        json.dump(sorted(handled), open(DONE_F, "w"))
        p("progress", progressed, stats, f"{(time.time() - CE.T0) / 60:.0f} min")
    left = sum(1 for r in done.values() if r.get("v") == 1 and not r.get("skip") and r["key"] not in handled)
    json.dump({"remaining": left, "progressed": progressed, "stats": stats, "dry": DRY}, open(STATE_F, "w"))
    p("end:", stats, "remaining", left)

if __name__ == "__main__":
    try: main()
    finally:
        publish(); sys.stdout.flush()
        os._exit(0)      # abandoned reader threads must not keep the job alive
