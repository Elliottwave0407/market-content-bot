"""Concall fact extraction (free): BSE earnings-call transcripts -> verified, quoted facts per company, saved to store/concall_facts/<YYYY-MM>.jsonl.
Unattended and resumable: a cursor file store/concall_facts/_cursor.json holds head (newest day done) and back (oldest day done going backwards to FLOOR).
Each run: (1) new days after head up to today, (2) then older days going backwards until the time budget ends.
Every kept item carries an EXACT quote that code found word-for-word in the transcript; unverified items are dropped. Numbers not present in the quote are removed.
Posts nothing anywhere. Key from env NVIDIA_API_KEY (never printed). Stores facts and short quotes only, not transcripts."""
import os, sys, re, json, time, glob, threading
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import store
import news_posts as NP
import concall_themes as CT

NV = os.environ.get("NVIDIA_API_KEY", "").strip()
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "150"))
WORKERS = int(os.environ.get("WORKERS", "3"))
FLOOR = os.environ.get("FLOOR", "2024-04-01")
MODELS = [m for m in os.environ.get("MODELS", "deepseek-ai/deepseek-v4.1-flash,nvidia/nemotron-3-ultra-550b-a55b").split(",") if m]
CHUNK = 60000
MAX_CHUNKS = 3
SCHEMA_V = 1
IST = timezone(timedelta(hours=5, minutes=30))
DIR = os.path.join(store.ROOT, "concall_facts")
CUR = os.path.join(DIR, "_cursor.json")
LOCK = threading.Lock()
T0 = time.time()

PROMPT = """You read an Indian listed company's earnings-call transcript. Extract what MANAGEMENT (not analysts) said. Return ONLY JSON:
{"items":[{"cat":"guidance|capex|order_book|margin|pricing_cost|demand|product_mix|risk|fund_raise|other","statement":"short plain summary (max 30 words)","period":"e.g. FY27, Q3 FY26, next quarter, or null","value":"number or range exactly as stated, or null","direction":"up|down|flat|null","quote":"EXACT sentence copied word for word from the transcript, under 300 characters"}]}
Rules: up to 14 items, the most decision-relevant ones (forward guidance with numbers first, then capex, order book, margins, price increases or cost pass-through, demand outlook, mix shift, risks). Every quote must be copied word for word. Do not invent numbers. If nothing relevant is said, return {"items":[]}. No investment advice."""

def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def prep(text):
    t = text or ""
    m = re.search(r"(good morning|good afternoon|good evening|ladies and gentlemen|welcome to the)", t[:20000], re.I)
    if m and m.start() > 300:
        t = t[m.start():]
    return re.sub(r"[ \t]+", " ", t)

def chunks(t):
    if len(t) <= CHUNK + 10000:
        return [t]
    n = min(MAX_CHUNKS, -(-len(t) // CHUNK))
    step = len(t) // n
    return [t[i * step:(i + 1) * step + 2000] for i in range(n)]

def call(model, text):
    extra = {"thinking": False} if "deepseek" in model else {"enable_thinking": False}
    for attempt in range(3):
        try:
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + NV}, timeout=300,
                              json={"model": model, "messages": [{"role": "user", "content": PROMPT + "\n\nTRANSCRIPT:\n" + text}],
                                    "max_tokens": 5000, "temperature": 0, "chat_template_kwargs": extra})
            if r.status_code in (429, 502, 503, 504):
                time.sleep(15 * (attempt + 1)); continue
            if r.status_code != 200:
                return None
            s = r.json()["choices"][0]["message"].get("content") or ""
            s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
            m = re.search(r"\{.*\}", s, re.S)
            return json.loads(m.group(0)) if m else None
        except Exception:
            time.sleep(8)
    return None

def verify(items, text):
    nt = norm(text); out = []; seen = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        q = str(it.get("quote") or "").strip()
        nq = norm(q)
        if len(nq) < 20 or nq not in nt or nq in seen:
            continue
        seen.add(nq)
        v = it.get("value")
        if v:
            for n in re.findall(r"\d[\d.,]*", str(v)):
                n = n.strip(".,").replace(",", "")
                if n and n not in q.replace(",", ""):
                    v = None; break
        out.append({"cat": str(it.get("cat") or "other")[:20], "statement": str(it.get("statement") or "")[:240], "period": it.get("period"),
                    "value": v, "direction": it.get("direction"), "quote": q[:320]})
    return out

def extract(x):
    code = str(x.get("SCRIP_CD")).strip(); day = (x.get("NEWS_DT") or "")[:10]
    nm = (x.get("SLONGNAME") or "").strip()
    base = {"key": f"{code}|{day}", "code": code, "name": nm, "day": day, "v": SCHEMA_V, "src": NP.link(x)}
    txt = CT.pdf_text(base["src"])
    if not txt:
        return {**base, "skip": "no_text"}
    t = prep(txt)
    if len(t.split()) < 1500:
        return {**base, "skip": "short_or_scanned", "words": len(t.split())}
    raw, used, bad = [], None, 0
    for ch in chunks(t):
        got = None
        for m in MODELS:
            got = call(m, ch)
            if got is not None:
                used = used or m.split("/")[-1]; break
        if got is None:
            bad += 1; continue
        raw += got.get("items") or []
    if bad == len(chunks(t)):
        return None   # all calls failed: retry in a later run, do not record
    ok = verify(raw, t)
    return {**base, "words": len(t.split()), "model": used, "n_raw": len(raw), "n_ok": len(ok), "items": ok, "at": datetime.now(IST).strftime("%Y-%m-%d %H:%M")}

def load_done():
    done = {}
    for f in glob.glob(os.path.join(DIR, "????-??.jsonl")):
        for ln in open(f, encoding="utf-8"):
            try:
                r = json.loads(ln); done[r["key"]] = r
            except Exception:
                pass
    return done

def save(done):
    os.makedirs(DIR, exist_ok=True)
    by = {}
    for r in done.values():
        by.setdefault((r.get("day") or "0000-00")[:7], []).append(r)
    for m, rows in by.items():
        rows.sort(key=lambda r: (r.get("day") or "", r.get("code") or ""))
        tmp = os.path.join(DIR, f"{m}.jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, os.path.join(DIR, f"{m}.jsonl"))

def cursor():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        c = json.load(open(CUR))
    except Exception:
        c = {"head": today, "back": (datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d")}
    return c, today

def out_of_time():
    return (time.time() - T0) / 60 > BUDGET_MIN

def run_day(day, done):
    rows = CT.find(day, day)
    todo = [x for x in rows if f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}" not in done]
    n_new = n_items = n_skip = n_fail = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {}
        for x in todo:
            futs[ex.submit(extract, x)] = x
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception:
                r = None
            if r is None:
                n_fail += 1; continue
            with LOCK:
                done[r["key"]] = r
            if r.get("skip"): n_skip += 1
            else: n_new += 1; n_items += r.get("n_ok", 0)
    return len(rows), n_new, n_items, n_skip, n_fail

def main():
    if not NV:
        p("NVIDIA_API_KEY missing"); return
    done = load_done(); c, today = cursor()
    p("start: done", len(done), "head", c["head"], "back", c["back"], "budget_min", BUDGET_MIN)
    # (1) new days since head
    d = datetime.fromisoformat(c["head"]) + timedelta(days=1)
    end = datetime.fromisoformat(today)
    while d <= end and not out_of_time():
        if d.weekday() < 5:
            r = run_day(d.strftime("%Y-%m-%d"), done); p("NEW", d.date(), "rows/new/items/skip/fail", r)
            save(done)
        c["head"] = d.strftime("%Y-%m-%d"); d += timedelta(days=1)
    # (2) older days backwards
    b = datetime.fromisoformat(c["back"]) - timedelta(days=1)
    floor = datetime.fromisoformat(FLOOR)
    while b >= floor and not out_of_time():
        if b.weekday() < 5:
            r = run_day(b.strftime("%Y-%m-%d"), done); p("BACK", b.date(), "rows/new/items/skip/fail", r)
            save(done)
        c["back"] = b.strftime("%Y-%m-%d"); b -= timedelta(days=1)
        json.dump(c, open(CUR, "w"))
    save(done)
    os.makedirs(DIR, exist_ok=True); json.dump(c, open(CUR, "w"))
    items = sum(r.get("n_ok", 0) for r in done.values())
    p("end: transcripts", sum(1 for r in done.values() if not r.get("skip")), "skipped", sum(1 for r in done.values() if r.get("skip")), "items", items, "cursor", c, f"{(time.time()-T0)/60:.0f} min")

if __name__ == "__main__":
    try:
        main()
    finally:
        publish()
