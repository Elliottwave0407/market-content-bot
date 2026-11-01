"""Vision bake-off on presentation slides (free models only, posts nothing, changes no store).
Sample: slides that carry pictures AND a text layer (so the text layer gives the known numbers). Each candidate reads the same slide IMAGES and lists the numbers it sees.
Score: recall of text-layer numbers, share of numbers NOT in the text layer (fabricated or picture-only: samples printed for review), seconds/slide, failures.
Env: N_SLIDES (40), NV_MODELS (comma list; blank = auto-discover vision models on NVIDIA), GEMINI (comma list), MISTRAL (comma list), WORKERS (3)."""
import os, sys, re, json, glob, time, base64, random, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
import requests, fitz
from ci_out import p, publish
import store
NV = os.environ.get("NVIDIA_API_KEY", "").strip(); GK = os.environ.get("GEMINI_API_KEY_CONCALL", "").strip(); MK = os.environ.get("MISTRAL_API_KEY", "").strip()
N = int(os.environ.get("N_SLIDES") or "40"); W = int(os.environ.get("WORKERS") or "3")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
PROMPT = """This is one slide from an Indian listed company's investor presentation. List every number you can SEE on the slide (tables, charts, labels, callouts) together with the label printed next to it. Copy numbers exactly as printed. Do not calculate, estimate or infer anything. If a number is unclear, leave it out. Return ONLY JSON: {"items":[{"label":"text printed next to the number","value":"number exactly as printed","period":"period if printed, else null"}]}"""
NUM = re.compile(r"\d[\d,]*\.?\d*")
def nums(s): return {n.replace(",", "").rstrip(".") for n in NUM.findall(s or "") if len(n.replace(",", "").rstrip(".")) >= 2}

# ---- sample slides
recs = []
for f in sorted(glob.glob(os.path.join(store.ROOT, "ppt_facts*", "20*.jsonl")), reverse=True):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("status") == "read" and r.get("visual_slides") and r.get("url"): recs.append(r)
random.Random(11).shuffle(recs); slides = []
for r in recs:
    if len(slides) >= N: break
    try:
        c = requests.get(r["url"], headers={**H, "Referer": "https://www.bseindia.com/" if r.get("exch") == "bse" else "https://www.nseindia.com/"}, timeout=60).content
        d = fitz.open(stream=c, filetype="pdf")
    except Exception: continue
    got = 0
    for i in range(min(d.page_count, 60)):
        pg = d[i]; t = pg.get_text(); w = len(t.split())
        if not (40 <= w <= 300): continue
        try: has_img = bool(pg.get_image_info()) or len(pg.get_drawings()) > 20
        except Exception: has_img = False
        if not has_img or len(nums(t)) < 4: continue
        png = pg.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("jpeg", jpg_quality=82)
        slides.append({"id": f"{r['name'][:20]}|{i+1}", "truth": nums(t), "b64": base64.b64encode(png).decode()}); got += 1
        if got >= 2: break
p("slides sampled", len(slides), "from decks", len(recs), "| median truth numbers", int(statistics.median(len(s["truth"]) for s in slides)) if slides else 0)
if not slides: publish(); os._exit(0)

def parse(s):
    s = re.sub(r"<think>.*?</think>", "", s or "", flags=re.S); m = re.search(r"\{.*\}", s, re.S)
    try: return json.loads(m.group(0)).get("items") or []
    except Exception: return None
def oai(url, key, model, b64):
    for a in range(4):
        try:
            r = requests.post(url, headers={"Authorization": "Bearer " + key}, timeout=180, json={"model": model, "temperature": 0, "max_tokens": 3000, "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]})
            if r.status_code in (429, 502, 503): time.sleep(15 * (a + 1)); continue
            if r.status_code != 200: return None, "http%d %s" % (r.status_code, r.text[:80])
            return parse(r.json()["choices"][0]["message"].get("content")), ""
        except Exception as e: time.sleep(5); err = type(e).__name__
    return None, "retries"
def gem(model, b64):
    for a in range(4):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GK}", timeout=120, json={"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 3000}})
            if r.status_code in (429, 503): time.sleep(20 * (a + 1)); continue
            if r.status_code != 200: return None, "http%d %s" % (r.status_code, "")
            return parse("".join(x.get("text", "") for x in r.json()["candidates"][0]["content"]["parts"])), ""
        except Exception: time.sleep(5)
    return None, "retries"
cands = []
nvm = [m for m in (os.environ.get("NV_MODELS") or "").split(",") if m]
if not nvm and NV:
    try:
        ids = sorted(x["id"] for x in requests.get("https://integrate.api.nvidia.com/v1/models", headers={"Authorization": "Bearer " + NV}, timeout=60).json()["data"])
        nvm = [m for m in ids if re.search(r"vl|vision|pixtral|gemma-3|phi-4-multimodal|llama-3.2-.*-vision|llama-4|kimi|qwen.*vl", m, re.I)][:8]
    except Exception as e: p("nvidia list failed", type(e).__name__)
p("NVIDIA vision candidates:", nvm)
for m in nvm: cands.append(("nv:" + m, lambda b, m=m: oai("https://integrate.api.nvidia.com/v1/chat/completions", NV, m, b)))
for m in [x for x in (os.environ.get("GEMINI") or "").split(",") if x]: cands.append(("gemini:" + m, lambda b, m=m: gem(m, b)))
for m in [x for x in (os.environ.get("MISTRAL") or "").split(",") if x]: cands.append(("mistral:" + m, lambda b, m=m: oai("https://api.mistral.ai/v1/chat/completions", MK, m, b)))
rows = []
for name, fn in cands:
    t0 = time.time(); res = {}
    def one(s):
        t = time.time(); it, err = fn(s["b64"]); return s["id"], it, err, time.time() - t
    try:
        with ThreadPoolExecutor(W) as ex:
            first = list(ex.map(one, slides[:2]))
            if all(x[1] is None for x in first): p(name, "unusable:", first[0][2]); continue
            allr = first + list(ex.map(one, slides[2:]))
    except Exception as e: p(name, "crashed", type(e).__name__); continue
    fails = sum(1 for x in allr if x[1] is None); rec = []; extra = []; nm_ = nt = 0; samples = []
    for (sid, it, err, sec), s in zip(allr, slides):
        if it is None: continue
        got = nums(" ".join(str(i.get("value") or "") for i in it if isinstance(i, dict)))
        nt += len(s["truth"]); nm_ += len(s["truth"] & got); extra.append(len(got - s["truth"])); rec.append(len(got))
        if got - s["truth"] and len(samples) < 4: samples.append((sid, sorted(got - s["truth"])[:6]))
    rows.append((name, round(statistics.median([x[3] for x in allr]), 1), fails, round(nm_ / max(1, nt), 2), round(sum(extra) / max(1, sum(rec)), 2), samples))
    p("done", name, f"{(time.time()-t0)/60:.1f} min")
p("=== VISION BAKE-OFF (same slide images) ===")
p("model | sec/slide | failed | recall of text-layer numbers | share of numbers not in text layer")
for r in rows: p(r[0], "|", r[1], "|", f"{r[2]}/{len(slides)}", "|", r[3], "|", r[4])
for r in rows: p("samples not in text layer", r[0], r[5])
publish()
