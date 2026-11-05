"""Independent audit of STORED investor-presentation facts (read-only on the facts; posts nothing).
Layer A (free, all records): value digits present in quote, statement numbers present in quote, short quotes, duplicates, items per presentation.
Layer B (sample): a DIFFERENT model family (Gemini flash-lite, separate concall-lane key) re-reads each sampled fact with the text of the slide it came from
         and says whether the QUOTE alone supports the STATEMENT, VALUE and PERIOD (yes/partial/no).
Output: store/ppt_audit/audit_<time>.json (every judged item) + printed summary. Env: DOCS (presentations per run, default 25), PER_DOC (facts judged per presentation, default 6), BUDGET_MIN."""
import os, sys, re, json, glob, time, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import store

GK = os.environ.get("GEMINI_API_KEY_CONCALL", "").strip()
DOCS = int(os.environ.get("DOCS") or "25"); PER = int(os.environ.get("PER_DOC") or "6"); BUDGET = float(os.environ.get("BUDGET_MIN") or "40"); T0 = time.time()
OUT = os.path.join(store.ROOT, "ppt_audit"); os.makedirs(OUT, exist_ok=True)
NUM = re.compile(r"\d[\d,]*\.?\d*")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*"}

def nums(s): return {n.replace(",", "").rstrip(".") for n in NUM.findall(s or "")}

recs = []
for f in sorted(glob.glob(os.path.join(store.ROOT, "ppt_facts", "20*.jsonl"))):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("items"): recs.append(r)
p("presentations with facts:", len(recs))

A = collections.Counter()
for r in recs:
    seen = set(); A["docs"] += 1; A["items"] += len(r["items"])
    for it in r["items"]:
        q = it.get("quote") or ""; v = str(it.get("value") or ""); st = it.get("statement") or ""
        if v and nums(v) and not nums(v) <= nums(q): A["value_not_in_quote"] += 1
        st2 = re.sub(r"\b(FY|CY|H|Q)\s?-?\d{1,4}\b|\b(19|20)\d\d\b|\b\d{1,2}(st|nd|rd|th)\b", " ", st)
        qn = q.replace(",", "")
        if any(n.strip(".,").replace(",", "") not in qn for n in re.findall(r"\d[\d.,]*", st2) if len(n.strip(".,")) >= 2): A["stmt_num_not_in_quote"] += 1
        if len(q) < 15: A["short_quote"] += 1
        k = q[:60].lower()
        if k in seen: A["duplicate_quote"] += 1
        seen.add(k)
p("=== LAYER A: structural checks (all stored presentation facts) ===")
p(f"docs {A['docs']} | items {A['items']} | " + " | ".join(f"{c} {A[c]} ({A[c]/max(A['items'],1):.1%})" for c in ("value_not_in_quote", "stmt_num_not_in_quote", "short_quote", "duplicate_quote")))

JP = """You audit facts extracted from an Indian company's investor presentation slide. For each numbered item you get the extracted STATEMENT (with value/period) and the QUOTE the extractor claims supports it, plus the text of the slide (CONTEXT).
Return ONLY JSON: {"r":[{"i":<n>,"support":"yes|partial|no","note":"max 12 words"}]}
support = does the QUOTE (read in the slide context) fully justify the STATEMENT, VALUE and PERIOD? yes = exactly; partial = statement adds scope/units/timing/direction the quote does not state, or mixes things; no = contradicts or unsupported.
Be strict. Do not use outside knowledge."""

def judge(batch):
    body = "".join(f"\n#{i}\nSTATEMENT: {b['statement']} | value={b.get('value')} | period={b.get('period')} | direction={b.get('direction')}\nQUOTE: {b['quote']}\nCONTEXT: {b['ctx']}\n" for i, b in enumerate(batch))
    for attempt in range(4):
        try:
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent", timeout=200,
                              headers={"x-goog-api-key": GK, "Content-Type": "application/json"},
                              json={"contents": [{"parts": [{"text": JP + "\n" + body}]}],
                                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 4000}})
            if r.status_code in (429, 500, 503):
                if r.status_code == 429 and "PerDay" in r.text: return "daily"
                time.sleep(10 * (attempt + 1)); continue
            if r.status_code != 200: return None
            m = re.search(r"\{.*\}", r.json()["candidates"][0]["content"]["parts"][0].get("text", ""), re.S)
            return {x["i"]: x for x in json.loads(m.group(0))["r"]}
        except Exception:
            time.sleep(6)
    return None

def slide_texts(url):
    import fitz
    c = b""
    for _ in range(2):
        try:
            c = requests.get(url, headers=UA, timeout=60).content
            if c[:4] == b"%PDF": break
        except Exception: pass
    if c[:4] != b"%PDF": return None
    d = fitz.open(stream=c, filetype="pdf")
    return [d[i].get_text() for i in range(d.page_count)]

if not GK:
    p("no GEMINI_API_KEY_CONCALL - Layer B skipped"); publish(); sys.exit(0)

DONE = set()
for f in glob.glob(os.path.join(OUT, "audit_*.json")):
    try:
        for j in json.load(open(f, encoding="utf-8")): DONE.add(j["key"])
    except Exception: pass
p("presentations already audited:", len(DONE))
rnd = random.Random(int(time.time()) // 600)
pool = [r for r in recs if r["key"] not in DONE and r.get("url")]
pool.sort(key=lambda r: r.get("day", ""), reverse=True)      # newest first
rnd.shuffle(pool[:400])
judged, picked, NOCTX = [], [], 0
for r in pool[:DOCS]:
    if (time.time() - T0) / 60 > BUDGET: break
    try: sl = slide_texts(r["url"])
    except Exception: sl = None
    if not sl: continue
    its = r["items"][:]; rnd.shuffle(its)
    for it in its[:PER]:
        s = it.get("slide")
        ctx = (sl[s - 1] if isinstance(s, int) and 0 < s <= len(sl) else "")
        if not ctx or re.sub(r"\s+", "", (it.get("quote") or ""))[:30].lower() not in re.sub(r"\s+", "", ctx).lower():
            NOCTX += 1; continue
        picked.append({**it, "ctx": re.sub(r"\s+", " ", ctx)[:1800], "name": r["name"], "day": r["day"], "key": r["key"]})
for k in range(0, len(picked), 12):
    if (time.time() - T0) / 60 > BUDGET: break
    res = judge(picked[k:k + 12])
    if res == "daily": p("Gemini daily limit reached on concall key - stopping"); break
    if not res: continue
    for i, b in enumerate(picked[k:k + 12]):
        x = res.get(i) or res.get(str(i))
        if x: judged.append({**{kk: b.get(kk) for kk in ("name", "day", "key", "cat", "statement", "value", "period", "direction", "quote", "slide")}, "support": x.get("support"), "note": x.get("note")})
    time.sleep(4)
if judged: json.dump(judged, open(os.path.join(OUT, f"audit_{time.strftime('%Y-%m-%d_%H%M')}.json"), "w", encoding="utf-8"), ensure_ascii=False)
n = len(judged)
if n:
    c = collections.Counter(j["support"] for j in judged)
    p(f"=== LAYER B: independent judge on {n} facts from {len({j['key'] for j in judged})} presentations (quote not found on the slide, skipped: {NOCTX}) ===")
    p(f"support yes {c['yes']/n:.0%} | partial {c['partial']/n:.0%} | no {c['no']/n:.0%}")
else:
    p("no facts judged this run")
publish()
