"""Read-only: can the free Mistral key read concalls? Lists models, tiny test per model (status, latency, rate-limit headers), then a real extraction on 3 stored transcripts per working model with the same prompt + quote verification as concall_extract. Never prints the key. Posts nothing."""
import os, sys, time, json, gzip, glob, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import concall_extract as CE

KEY = os.environ.get("MISTRAL_API_KEY", "").strip()
BASE = "https://api.mistral.ai/v1"
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json", "Content-Type": "application/json"}
p("key present:", bool(KEY), "len>20:", len(KEY) > 20)
ids = []
try:
    r = requests.get(BASE + "/models", headers=H, timeout=40)
    p("list status", r.status_code)
    if r.status_code == 200:
        ids = sorted({m.get("id") for m in r.json().get("data", [])})
        p("models:", len(ids), ", ".join(ids)[:1800])
    else:
        p("list body", r.text[:200].replace("\n", " "))
except Exception as e:
    p("list error", repr(e)[:120])

ALL = os.environ.get("ALL") == "1"
if ALL:
    cands = [m for m in ids if not any(x in m for x in ("embed", "moderation", "ocr", "transcribe", "voxtral", "tts", "fim"))]
else:
  cands = [m for m in ("mistral-small-latest", "mistral-medium-latest", "mistral-large-latest", "open-mistral-nemo", "ministral-8b-latest", "magistral-small-latest") if m in ids] or ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"]
if ALL:
    p("testing", len(cands), "models")
good = []
for m in cands:
    t = time.time()
    try:
        r = requests.post(BASE + "/chat/completions", headers=H, timeout=60, json={"model": m, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 8, "temperature": 0})
        rl = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or "retry" in k.lower()}
        p("TEST", m, r.status_code, f"{time.time()-t:.1f}s", (r.text[:110].replace("\n", " ") if r.status_code != 200 else "ok"), json.dumps(rl)[:200])
        if r.status_code == 200:
            good.append(m)
    except Exception as e:
        p("TEST", m, "err", repr(e)[:80])
    time.sleep(1.2)

files = sorted(glob.glob(os.path.join(CE.store.ROOT, "concall_text", "*.txt.gz")))
random_pick = files[::max(1, len(files) // 3)][:3]
p("sample transcripts:", len(random_pick))

def call(model, text):
    t = time.time()
    r = requests.post(BASE + "/chat/completions", headers=H, timeout=180,
                      json={"model": model, "messages": [{"role": "user", "content": CE.PROMPT + "\n\nTRANSCRIPT:\n" + text}], "max_tokens": 5000, "temperature": 0, "response_format": {"type": "json_object"}})
    dt = time.time() - t
    if r.status_code != 200:
        return None, dt, r.status_code, 0
    j = r.json()
    s = j["choices"][0]["message"].get("content") or ""
    m = re.search(r"\{.*\}", s, re.S)
    try:
        return (json.loads(m.group(0)) if m else None), dt, 200, (j.get("usage") or {}).get("prompt_tokens", 0)
    except Exception:
        return None, dt, 200, 0

for m in (good[:3] if not ALL else []):
    for f in random_pick:
        try:
            txt = gzip.open(f, "rt", encoding="utf-8", errors="ignore").read()
        except Exception as e:
            p("read fail", repr(e)[:60]); continue
        t = CE.prep(txt)
        raw, dts, toks, bad = [], 0, 0, 0
        for ch in CE.chunks(t):
            got, dt, st, pt = call(m, ch)
            dts += dt; toks += pt
            if got is None:
                bad += 1; p("  call failed", m, st); continue
            raw += got.get("items") or []
            time.sleep(1.2)
        ok = CE.verify(raw, t)
        cats = sorted({i["cat"] for i in ok})
        p("EXTRACT", m, os.path.basename(f)[:18], f"words={len(t.split())}", f"raw={len(raw)} verified={len(ok)}", f"{dts:.0f}s", f"prompt_tokens={toks}", "bad_chunks=%d" % bad, "cats=" + ",".join(cats))
        if ok:
            p("   sample:", ok[0]["statement"][:150], "| quote:", ok[0]["quote"][:140])
publish()
