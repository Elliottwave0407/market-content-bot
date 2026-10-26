"""Fair head-to-head of concall readers on the SAME transcripts, same prompt, same quote verification (concall_extract.verify).
Readers: Mistral ministral-14b, NVIDIA deepseek, NVIDIA nemotron, Gemini (separate project key GEMINI_API_KEY_CONCALL only - never the result-card key).
Read-only: writes store/concall_compare_readers/results.json and prints a summary. Posts nothing."""
import os, sys, re, json, time, glob, random, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import concall_extract as CE
import concall_themes as CT

GK = os.environ.get("GEMINI_API_KEY_CONCALL", "").strip()
N = int(os.environ.get("N", "20"))
BUDGET = float(os.environ.get("BUDGET_MIN", "45"))
T0 = time.time()
OUT = os.path.join(CE.store.ROOT, "concall_compare_readers")

def gem(model):
    def f(text):
        for attempt in range(3):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", timeout=240,
                                  headers={"x-goog-api-key": GK, "Content-Type": "application/json"},
                                  json={"contents": [{"parts": [{"text": CE.PROMPT + "\n\nTRANSCRIPT:\n" + text}]}],
                                        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 8000}})
                if r.status_code in (429, 500, 503):
                    f.last = r.status_code
                    if r.status_code == 429 and "PerDay" in r.text:
                        return None
                    time.sleep(8 * (attempt + 1)); continue
                if r.status_code != 200:
                    f.last = r.status_code; return None
                s = r.json()["candidates"][0]["content"]["parts"][0].get("text") or ""
                m = re.search(r"\{.*\}", s, re.S)
                return json.loads(m.group(0)) if m else None
            except Exception as e:
                f.last = "err"; time.sleep(5)
        return None
    f.last = None
    return f

READERS = {}
if CE.MK: READERS["mistral-14b"] = lambda t: CE.call_mistral("ministral-14b-latest", t)
if CE.NV:
    READERS["deepseek"] = lambda t: CE.call("deepseek-ai/deepseek-v4.1-flash", t)
    READERS["nemotron"] = lambda t: CE.call("nvidia/nemotron-3-ultra-550b-a55b", t)
if GK:
    READERS["gemini-lite"] = gem("gemini-flash-lite-latest")
    READERS["gemini-flash"] = gem("gemini-flash-latest")
p("readers:", ", ".join(READERS), "| N", N)

# the same documents for everyone: random recent transcripts that deepseek already read (so the old store can be compared too)
live = []
for f in glob.glob(os.path.join(CE.store.ROOT, "concall_facts", "20*.jsonl")):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if not r.get("skip") and r.get("src") and 4000 <= r.get("words", 0) <= 12000 and r.get("day", "") >= "2026-08-01":
            live.append(r)
random.Random(5).shuffle(live)
docs = live[:N]
p("documents:", len(docs))

def one(d):
    if (time.time() - T0) / 60 > BUDGET:
        return None
    txt = CE.prep(CT.pdf_text(d["src"]) or "")
    if len(txt.split()) < 1500:
        return None
    chs = CE.chunks(txt)
    res = {"key": d["key"], "name": d["name"], "words": len(txt.split()), "chunks": len(chs), "readers": {}}
    for name, fn in READERS.items():
        t = time.time(); raw = []; fail = 0
        for ch in chs:
            got = fn(ch)
            if got is None: fail += 1; continue
            raw += got.get("items") or []
        ok = CE.verify(raw, txt)
        res["readers"][name] = {"secs": round(time.time() - t), "fail_chunks": fail, "n_raw": len(raw), "n_ok": len(ok),
                                "realigned": sum(1 for i in ok if i.get("realigned")), "flag": sum(1 for i in ok if i.get("flag")),
                                "cats": len({i["cat"] for i in ok}), "items": ok}
    p("DOC", d["name"][:22], {k: (v["n_ok"], v["n_raw"], v["secs"]) for k, v in res["readers"].items()})
    return res

with ThreadPoolExecutor(int(os.environ.get("DOCS_PAR", "4"))) as ex:
    results = [r for r in ex.map(one, docs) if r]
os.makedirs(OUT, exist_ok=True)
json.dump(results, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), ensure_ascii=False)
p("=== SUMMARY over", len(results), "documents (same docs, same prompt, same verifier) ===")
p("reader | docs ok(any items) | raw | verified | verified% | per-doc | median secs/doc | failed-chunks | realigned | flagged")
for name in READERS:
    rows = [r["readers"][name] for r in results if name in r["readers"]]
    good = [x for x in rows if x["n_raw"] > 0]
    raw = sum(x["n_raw"] for x in rows); ok = sum(x["n_ok"] for x in rows)
    secs = sorted(x["secs"] for x in rows)
    p(f"{name} | {len(good)}/{len(rows)} | {raw} | {ok} | {ok/max(raw,1):.0%} | {ok/max(len(rows),1):.1f} | {secs[len(secs)//2] if secs else 0} | {sum(x['fail_chunks'] for x in rows)} | {sum(x['realigned'] for x in rows)} | {sum(x['flag'] for x in rows)}")
publish()
