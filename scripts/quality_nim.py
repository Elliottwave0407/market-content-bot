"""Read-only extraction quality test: same transcripts, several free models. Scores: JSON validity, items, quotes found verbatim in the transcript, numbers in 'value' that appear in the quote.
Writes nothing to any group. Keys come from env (never printed)."""
import os, sys, re, gzip, glob, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests

NV = os.environ.get("NVIDIA_API_KEY", "").strip()
GK = os.environ.get("GEMINI_API_KEY", "").strip()
N_DOCS = int(os.environ.get("N_DOCS", "6"))
MAXC = 70000
NIM = ["nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3.5-lightning-30b-a3b", "deepseek-ai/deepseek-v4.1-flash"]
GEM = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]

PROMPT = """You read an Indian listed company's earnings-call transcript. Extract what MANAGEMENT said (not analysts). Return ONLY JSON:
{"guidance":[{"topic":"revenue|margin|volume|capex|order_book|pricing|cost|demand|other","statement":"short plain summary","period":"e.g. FY27, next quarter, or null","value":"number/range as stated or null","quote":"EXACT sentence copied from the transcript"}],
 "pricing_cost":[{"statement":"...","quote":"EXACT sentence"}],
 "risks":[{"statement":"...","quote":"EXACT sentence"}]}
Rules: max 6 guidance items, 3 pricing_cost, 3 risks. Every quote must be copied word for word from the transcript (one sentence, under 300 characters). If nothing is said, use an empty list. Do not invent numbers. No investment advice."""

def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def docs():
    out = []
    for f in sorted(glob.glob("store/concall_text/*.txt.gz")):
        t = gzip.open(f, "rt", errors="ignore").read()
        if "moderator" in t.lower() and len(t) > 30000:
            out.append((os.path.basename(f), t[:MAXC]))
    return out[:N_DOCS]

def call_nim(model, text):
    r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + NV}, timeout=240,
                      json={"model": model, "messages": [{"role": "user", "content": PROMPT + "\n\nTRANSCRIPT:\n" + text}], "max_tokens": 5000, "temperature": 0, "chat_template_kwargs": ({"thinking": False} if "deepseek" in model else {"enable_thinking": False})})
    if r.status_code != 200: return None, f"HTTP {r.status_code} {r.text[:80]}"
    return (r.json()["choices"][0]["message"].get("content") or ""), None

def call_gem(model, text):
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": GK}, timeout=240,
                      json={"contents": [{"parts": [{"text": PROMPT + "\n\nTRANSCRIPT:\n" + text}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 3500, "responseMimeType": "application/json"}})
    if r.status_code == 503:
        time.sleep(20)
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": GK}, timeout=240,
                          json={"contents": [{"parts": [{"text": PROMPT + "\n\nTRANSCRIPT:\n" + text}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 3500, "responseMimeType": "application/json"}})
    if r.status_code != 200: return None, f"HTTP {r.status_code}"
    try: return r.json()["candidates"][0]["content"]["parts"][0]["text"], None
    except Exception: return None, "no text"

def parse(s):
    s = re.sub(r"<think>.*?</think>", "", s or "", flags=re.S)
    m = re.search(r"\{.*\}", s, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def score(j, text):
    nt = norm(text); items = []
    for k in ("guidance", "pricing_cost", "risks"):
        for it in (j.get(k) or []):
            if isinstance(it, dict): items.append(it)
    tot = ok = numbad = 0
    for it in items:
        q = norm(str(it.get("quote") or ""))
        tot += 1
        if len(q) > 15 and q in nt: ok += 1
        v = str(it.get("value") or "")
        for n in re.findall(r"\d[\d.,]*", v):
            if n.strip(".,") and n.strip(".,") not in str(it.get("quote") or "").replace(",", "") and n.strip(".,").replace(",", "") not in str(it.get("quote") or "").replace(",", ""):
                numbad += 1
    return tot, ok, numbad

D = docs()
p("docs:", [(n, len(t)) for n, t in D])
res = {}
for name, text in D:
    for kind, models in (("nim", NIM), ("gem", GEM)):
        for m in models:
            if kind == "nim" and not NV: continue
            if kind == "gem" and not GK: continue
            t0 = time.time()
            try:
                raw, err = (call_nim if kind == "nim" else call_gem)(m, text)
            except Exception as e:
                raw, err = None, repr(e)[:60]
            dt = time.time() - t0
            if err or raw is None:
                p("RUN", name[:12], m.split("/")[-1], "ERR", err, f"{dt:.0f}s"); res.setdefault(m, []).append((0, 0, 0, 0, dt)); continue
            j = parse(raw)
            if not j:
                p("RUN", name[:12], m.split("/")[-1], "BAD JSON", f"{dt:.0f}s", len(raw)); res.setdefault(m, []).append((0, 0, 0, 0, dt)); continue
            tot, ok, nb = score(j, text)
            p("RUN", name[:12], m.split("/")[-1], f"items {tot} quotes_ok {ok} num_unsupported {nb}", f"{dt:.0f}s")
            res.setdefault(m, []).append((1, tot, ok, nb, dt))
            time.sleep(2)
p("SUMMARY (docs, json_ok, items, quotes_ok, num_unsupported, avg_sec)")
for m, rows in res.items():
    n = len(rows); jo = sum(r[0] for r in rows); it = sum(r[1] for r in rows); q = sum(r[2] for r in rows); nb = sum(r[3] for r in rows)
    p(m, n, jo, it, q, nb, f"{sum(r[4] for r in rows)/n:.0f}s")
publish()
