"""Read every investor presentation in store/ppt_listing/merged.jsonl (newest first), store verified facts + pointers to slides that hold numbers inside images.
Output store/ppt_facts/<YYYY-MM>.jsonl (one record per document), state _done.json. Env: MAXN, BUDGET_MIN, WORKERS, DRY (1 -> folder ppt_facts_dry), MODELS. Posts nothing.
Record: key, isin, name, day, src, url, pages, words, n_raw, n_ok, items (each with slide), visual_slides (pages with images/charts and little text = numbers may sit in pictures), status."""
import os, sys, re, io, json, time, collections
os.environ.setdefault("SCHEMA_V", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor, wait
import requests, fitz
from ci_out import p, publish
import concall_extract as CE
from ppt_prompt import PPT_PROMPT
CE.PROMPT = PPT_PROMPT; CE.MAXTOK = 6000
ROOT = CE.store.ROOT; DRY = os.environ.get("DRY", "") == "1"
D = os.path.join(ROOT, "ppt_facts_dry" if DRY else "ppt_facts"); os.makedirs(D, exist_ok=True)
STATE = os.path.join(D, "_done.json")
MAXN = int(os.environ.get("MAXN") or "0"); BUDGET = float(os.environ.get("BUDGET_MIN") or "140"); W = int(os.environ.get("WORKERS") or "10")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
S = {"nse": requests.Session(), "bse": requests.Session()}
S["nse"].headers.update({**H, "Referer": "https://www.nseindia.com/"}); S["bse"].headers.update({**H, "Referer": "https://www.bseindia.com/"})
try: S["nse"].get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=30)
except Exception: pass
T0 = time.time(); NUM = re.compile(r"\d"); WHY = collections.Counter()
def call_p(model, text):
    extra = {"enable_thinking": False}
    for attempt in range(7):
        try:
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + CE.NV}, timeout=300,
                              json={"model": model, "messages": [{"role": "user", "content": CE.PROMPT + "\n\nTRANSCRIPT:\n" + text}], "max_tokens": CE.MAXTOK, "temperature": 0, "chat_template_kwargs": extra})
            if r.status_code in (429, 502, 503, 504): WHY["http%d" % r.status_code] += 1; time.sleep(min(120, 20 * (attempt + 1))); continue
            if r.status_code != 200: WHY["http%d" % r.status_code] += 1; return None
            s = re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"].get("content") or "", flags=re.S)
            m = re.search(r"\{.*\}", s, re.S)
            if not m: WHY["nojson"] += 1; return None
            try: return json.loads(m.group(0))
            except Exception: WHY["badjson"] += 1; return None
        except requests.exceptions.Timeout: WHY["timeout"] += 1
        except Exception as e: WHY[type(e).__name__] += 1; time.sleep(8)
    return None

def fetch(urls):
    for src, u in urls:
        for a in range(2):
            try:
                r = S[src].get(u, timeout=90)
                if r.status_code == 200 and 3000 < len(r.content) < 60_000_000 and r.content[:4] == b"%PDF": return r.content
            except Exception: pass
            time.sleep(2)
    return None

def read(d):
    urls = [(d["src"], d["url"])] + [(a["src"], a["url"]) for a in d.get("alts", [])]
    c = fetch(urls)
    if not c: return {"status": "no_download"}
    try: doc = fitz.open(stream=c, filetype="pdf")
    except Exception: return {"status": "not_pdf"}
    n = doc.page_count; pages = []; vis = []
    for i in range(min(n, 120)):
        pg = doc[i]; t = pg.get_text(); w = len(t.split()); pages.append(t)
        try:
            area = pg.rect.width * pg.rect.height; imgarea = 0
            for im in pg.get_image_info(): b = im["bbox"]; imgarea += max(0, b[2] - b[0]) * max(0, b[3] - b[1])
            dr = len(pg.get_drawings()) if w < 120 else 0
            if w < 80 and (imgarea > 0.2 * area or dr > 25): vis.append(i + 1)
        except Exception: pass
    text = "\n".join(f"[slide {i+1}]\n{t}" for i, t in enumerate(pages)); words = len(text.split())
    base = {"pages": n, "words": words, "visual_slides": vis[:60]}
    if words < 400: return {**base, "status": "image_only" if vis or n else "empty", "items": [], "n_raw": 0, "n_ok": 0}
    raw, bad = [], 0; chs = CE.chunks(CE.prep(text)) if False else CE.chunks(text)
    t0 = time.time(); used = None
    for ch in chs:
        if time.time() - t0 > 14 * 60: bad += 1; continue
        got = None
        for mod in CE.MODELS:
            got = call_p(mod, ch)
            if got is not None: used = used or mod.split("/")[-1]; break
        if got is None: bad += 1; continue
        raw += got.get("items") or []
    if bad == len(chs): return None
    ok = CE.verify(raw, text)
    for it in ok:
        q = it.get("quote") or ""
        qn = CE.norm(q)[:50]
        it["slide"] = next((i + 1 for i, t in enumerate(pages) if qn and qn in CE.norm(t)), None)
    return {**base, "status": "read", "model": used, "chunks_failed": bad, "n_raw": len(raw), "n_ok": len(ok), "items": ok}

def main():
    if not CE.NV: p("no model key"); return
    docs = [json.loads(l) for l in open(os.path.join(ROOT, "ppt_listing", "merged.jsonl"), encoding="utf-8")]
    docs.sort(key=lambda x: x["day"], reverse=True)
    try: done = set(json.load(open(STATE)))
    except Exception: done = set()
    k = lambda d: f"{d['key']}|{d['day']}"
    todo = [d for d in docs if k(d) not in done]
    p("models:", ", ".join(m.split("/")[-1] for m in CE.MODELS), "| dry" if DRY else "| live", "| docs total", len(docs), "| to read", len(todo), "| workers", W)
    st = collections.Counter(); prog = 0; i = 0; nitems = 0
    def stop(): return (time.time() - T0) / 60 > BUDGET or (MAXN and prog >= MAXN)
    while i < len(todo) and not stop():
        part = todo[i:i + W * 2]; i += W * 2
        ex = ThreadPoolExecutor(W)
        try:
            futs = {ex.submit(read, d): d for d in part}
            wait(list(futs), timeout=30 * 60)
            for f, d in futs.items():
                if not f.done(): st["timeout"] += 1; continue
                try: r = f.result()
                except Exception: r = None
                if r is None: st["failed"] += 1; continue
                rec = {"key": k(d), "isin": d.get("isin"), "name": d.get("name"), "day": d["day"], "exch": d["src"], "url": d["url"], **r, "v": "ppt1"}
                with open(os.path.join(D, d["day"][:7] + ".jsonl"), "a", encoding="utf-8") as fh: fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done.add(k(d)); prog += 1; st[r["status"]] += 1; nitems += r.get("n_ok", 0)
        finally: ex.shutdown(wait=False, cancel_futures=True)
        json.dump(sorted(done), open(STATE, "w"))
        p("progress", prog, dict(st), "facts", nitems, f"{(time.time()-T0)/60:.0f} min")
    left = len(todo) - i if i < len(todo) else 0
    json.dump({"remaining": len(todo) - prog, "progressed": prog, "stats": dict(st)}, open(os.path.join(D, "_state.json"), "w"))
    p("failure reasons:", dict(WHY)); p("end:", dict(st), "remaining", len(todo) - prog)

if __name__ == "__main__":
    try: main()
    finally:
        publish(); sys.stdout.flush(); os._exit(0)
