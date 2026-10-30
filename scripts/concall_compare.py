"""Reader bake-off (free, posts nothing, changes no stored facts): the SAME transcripts are read by several NVIDIA NIM models with the v3 prompt;
code verifies the quotes; a different family (Gemini flash-lite, concall key) judges a blinded sample of each model's facts.
Reports per model: speed, failures, facts per transcript, quote-verified share, structural A-share, judged support, speaker=analyst share, numbers captured vs the union of all models.
Env: MODELS (comma list of NIM ids), N (transcripts, default 16), WORKERS (3), BUDGET_MIN, JUDGE_PER_DOC (default 10), FROM_DAY (default 2026-08-01)."""
import os, sys, re, json, time, random, collections, statistics
os.environ.setdefault("SCHEMA_V", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
from ci_out import p, publish
import requests
import concall_extract as CE
NV = os.environ.get("NVIDIA_API_KEY", "").strip(); GK = os.environ.get("GEMINI_API_KEY_CONCALL", "").strip()
MODELS = [m for m in (os.environ.get("MODELS") or "nvidia/nemotron-3-ultra-550b-a55b,deepseek-ai/deepseek-v4.1-flash").split(",") if m]
N = int(os.environ.get("N") or "16"); W = int(os.environ.get("WORKERS") or "3"); BUDGET = float(os.environ.get("BUDGET_MIN") or "110")
JPD = int(os.environ.get("JUDGE_PER_DOC") or "10"); FROM_DAY = os.environ.get("FROM_DAY") or "2026-08-01"
T0 = time.time(); OUT = os.path.join(CE.store.ROOT, "concall_compare"); os.makedirs(OUT, exist_ok=True)

def call_nv(model, text):
    """returns (items or None, seconds, note)"""
    t0 = time.time(); extra = {"thinking": False} if "deepseek" in model else {"enable_thinking": False}; note = ""
    for attempt in range(3):
        try:
            body = {"model": model, "messages": [{"role": "user", "content": CE.PROMPT + "\n\nTRANSCRIPT:\n" + text}], "max_tokens": CE.MAXTOK, "temperature": 0}
            if extra is not None: body["chat_template_kwargs"] = extra
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + NV}, timeout=240, json=body)
            if r.status_code == 400 and extra is not None: extra = None; note = "no_kwargs"; continue
            if r.status_code in (429, 502, 503, 504): note = f"http{r.status_code}"; time.sleep(15 * (attempt + 1)); continue
            if r.status_code != 200: return None, time.time() - t0, f"http{r.status_code}"
            s = r.json()["choices"][0]["message"].get("content") or ""
            s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
            for cand in (re.search(r"\{.*\}", s, re.S), re.search(r"\{\s*\"items\".*\}", s, re.S)):
                if cand:
                    try: return (json.loads(cand.group(0)).get("items") or []), time.time() - t0, note
                    except Exception: pass
            return None, time.time() - t0, "badjson"
        except requests.exceptions.Timeout: note = "timeout"
        except Exception as e: note = type(e).__name__; time.sleep(5)
    return None, time.time() - t0, note or "fail"

# ---- sample: same transcripts for every model
done = CE.load_done(); mc = {}
try: sect = json.load(open(os.path.join(CE.store.ROOT, "sector_map", "sector_map.json")))
except Exception: sect = {}
pool = [r for r in done.values() if not r.get("skip") and r.get("day", "") >= FROM_DAY and r.get("src")]
rnd = random.Random(11); rnd.shuffle(pool)
fin = [r for r in pool if "Financ" in str((sect.get(r["code"]) or {}).get("nse_sector") or (sect.get(r["code"]) or {}).get("yf_sector") or "")]
oth = [r for r in pool if r not in fin]
pick = (fin[: max(1, N // 4)] + oth)[:N]
docs = []
for r in pick:
    try: t = CE.prep(CE.CT.pdf_text(r["src"]) or "")
    except Exception: continue
    if len(t.split()) >= 1000: docs.append({"key": r["key"], "name": r["name"], "day": r["day"], "text": t})
p("transcripts:", len(docs), "| words median", int(statistics.median(len(d["text"].split()) for d in docs)), "| models:", ", ".join(m.split("/")[-1] for m in MODELS))

res = {m: {} for m in MODELS}
def run_doc(m, d):
    raw, secs, fails, notes = [], [], 0, collections.Counter()
    for ch in CE.chunks(d["text"]):
        items, s, note = call_nv(m, ch)
        secs.append(s)
        if note: notes[note] += 1
        if items is None: fails += 1; continue
        raw += items
    ok = CE.verify(raw, d["text"]) if raw else []
    return {"n_raw": len(raw), "n_ok": len(ok), "secs": round(sum(secs), 1), "chunks": len(secs), "fails": fails, "notes": dict(notes), "items": ok}
for m in MODELS:
    if (time.time() - T0) / 60 > BUDGET * 0.6: p("budget: skipping", m); continue
    t_m = time.time()
    with ThreadPoolExecutor(W) as ex:
        futs = {d["key"]: ex.submit(run_doc, m, d) for d in docs}
        for k, f in futs.items():
            try: res[m][k] = f.result(timeout=max(60, BUDGET * 60 * 0.6 - (time.time() - T0)))
            except Exception as e: res[m][k] = {"n_raw": 0, "n_ok": 0, "secs": 0, "chunks": 0, "fails": 1, "notes": {"exc": 1}, "items": []}
    p(m.split("/")[-1], "done in", round((time.time() - t_m) / 60), "min")

# ---- numbers captured vs union (recall proxy)
NUM = re.compile(r"\d[\d,]*\.?\d*")
def nset(items): return {n.replace(",", "").rstrip(".") for it in items for n in NUM.findall(it.get("quote") or "") if len(n.replace(",", "")) >= 2}
# ---- structural grade
def sgrade(it):
    q = it.get("quote") or ""; v = str(it.get("value") or ""); st = it.get("statement") or ""; iss = 0
    st2 = re.sub(r"\b(FY|CY|H|Q)\s?-?\d{1,4}\b|\b(19|20)\d\d\b|\b\d{1,2}(st|nd|rd|th)\b", " ", st); qn = q.replace(",", "")
    if any(n.strip(".,").replace(",", "") not in qn for n in re.findall(r"\d[\d.,]*", st2) if len(n.strip(".,")) >= 2): iss += 1
    if v and not {n.replace(",", "").rstrip(".") for n in NUM.findall(v)} <= {n.replace(",", "").rstrip(".") for n in NUM.findall(q)}: iss += 1
    if it.get("realigned"): iss += 1
    if len(q) < 40: iss += 1
    if not it.get("period") and it.get("cat") in ("guidance", "capex", "order_book"): iss += 1
    g = "A" if iss == 0 else ("B" if iss == 1 else "C")
    return "C" if "?" in q else g

# ---- blinded judge
JP = """You audit facts extracted from an Indian company's earnings call. For each numbered item you get the extracted STATEMENT (with value/period) and the QUOTE the extractor claims supports it, plus the transcript text around the quote (CONTEXT).
Return ONLY JSON: {"r":[{"i":<n>,"support":"yes|partial|no","speaker":"mgmt|analyst|unclear","note":"max 12 words"}]}
support = does the QUOTE alone fully justify the STATEMENT, VALUE and PERIOD? yes = exactly; partial = statement adds scope/units/timing/direction the quote does not state, or mixes things; no = contradicts or unsupported.
speaker = is the quote spoken by company management (mgmt) or by an analyst/question-asker (analyst); unclear if the context does not show.
Be strict. Do not use outside knowledge."""
def ctx_for(text, quote):
    idx = [i for i, ch in enumerate(text) if not ch.isspace()]; comp = "".join(text[i] for i in idx).lower(); k = re.sub(r"\s+", "", quote)[:45].lower(); j = comp.find(k)
    if j < 0: return None
    i = idx[j]; return text[max(0, i - 500): i + len(quote) + 300].replace("\n", " ")
def judge(batch):
    body = "".join(f"\n#{i}\nSTATEMENT: {b['statement']} | value={b.get('value')} | period={b.get('period')} | direction={b.get('direction')}\nQUOTE: {b['quote']}\nCONTEXT: {b['ctx']}\n" for i, b in enumerate(batch))
    for attempt in range(4):
        try:
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent", timeout=200, headers={"x-goog-api-key": GK, "Content-Type": "application/json"},
                              json={"contents": [{"parts": [{"text": JP + "\n" + body}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 6000}})
            if r.status_code in (429, 500, 503):
                if r.status_code == 429 and "PerDay" in r.text: return "daily"
                time.sleep(10 * (attempt + 1)); continue
            if r.status_code != 200: return None
            m_ = re.search(r"\{.*\}", r.json()["candidates"][0]["content"]["parts"][0].get("text", ""), re.S)
            return {x["i"]: x for x in json.loads(m_.group(0))["r"]}
        except Exception: time.sleep(6)
    return None
text_of = {d["key"]: d["text"] for d in docs}; rj = random.Random(5)
jud = {m: [] for m in MODELS}; daily = False
if GK:
    for m in MODELS:
        picked = []
        for k, rr in res[m].items():
            its = rr["items"][:]; rj.shuffle(its)
            for it in its[:JPD]:
                c = ctx_for(text_of[k], it["quote"])
                if c: picked.append({**it, "ctx": c})
        for i in range(0, len(picked), 12):
            if daily or (time.time() - T0) / 60 > BUDGET: break
            out = judge(picked[i:i + 12])
            if out == "daily": daily = True; p("Gemini daily limit reached"); break
            if not out: continue
            for j, b in enumerate(picked[i:i + 12]):
                x = out.get(j) or out.get(str(j))
                if x: jud[m].append({"support": x.get("support"), "speaker": x.get("speaker")})
            time.sleep(4)
else: p("no GEMINI_API_KEY_CONCALL: judge skipped")

# ---- table
p("=== READER BAKE-OFF (same transcripts, v3 prompt) ===")
p("model | docs ok | sec/doc | chunk fails | facts/doc | verified of raw | struct A | judged n | yes | partial | no | analyst voice | numbers captured vs union")
summary = {}
for m in MODELS:
    rs = [r for r in res[m].values()]
    if not rs: continue
    n = len(rs); raw = sum(r["n_raw"] for r in rs); ok = sum(r["n_ok"] for r in rs); allit = [it for r in rs for it in r["items"]]
    ga = sum(1 for it in allit if sgrade(it) == "A") / max(1, len(allit)); js = jud[m]; c = collections.Counter(x["support"] for x in js); sp = collections.Counter(x["speaker"] for x in js)
    cov = []
    for k in text_of:
        U = set().union(*[nset(res[mm][k]["items"]) for mm in MODELS if k in res[mm]])
        if U and k in res[m]: cov.append(len(nset(res[m][k]["items"]) & U) / len(U))
    ch = sum(r["chunks"] for r in rs); fl = sum(r["fails"] for r in rs)
    s = {"docs": n, "sec_per_doc": round(sum(r["secs"] for r in rs) / n), "chunk_fails": f"{fl}/{ch}", "facts_per_doc": round(ok / n, 1), "verified_of_raw": round(ok / max(1, raw), 2), "struct_A": round(ga, 2),
         "judged": len(js), "yes": round(c["yes"] / max(1, len(js)), 2), "partial": round(c["partial"] / max(1, len(js)), 2), "no": round(c["no"] / max(1, len(js)), 2), "analyst": round(sp["analyst"] / max(1, len(js)), 2),
         "numbers_vs_union": round(statistics.mean(cov), 2) if cov else None, "notes": dict(collections.Counter(k for r in rs for k in r["notes"]))}
    summary[m] = s
    p(m.split("/")[-1], "|", n, "|", s["sec_per_doc"], "|", s["chunk_fails"], "|", s["facts_per_doc"], "|", s["verified_of_raw"], "|", s["struct_A"], "|", s["judged"], "|", s["yes"], "|", s["partial"], "|", s["no"], "|", s["analyst"], "|", s["numbers_vs_union"], "| notes", s["notes"])
day = time.strftime("%Y-%m-%d_%H%M")
json.dump({"summary": summary, "per_doc": {m: {k: {kk: vv for kk, vv in r.items() if kk != "items"} for k, r in res[m].items()} for m in MODELS}, "docs": [{"key": d["key"], "name": d["name"], "day": d["day"]} for d in docs]}, open(os.path.join(OUT, f"compare_{day}.json"), "w"), indent=1)
p("minutes", round((time.time() - T0) / 60)); publish()
