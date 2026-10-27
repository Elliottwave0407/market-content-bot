"""Independent audit of STORED concall facts (read-only on the facts; posts nothing).
Layer A (free, all records): structural checks per reader - numbers in value/statement present in quote, quote length, question-style quotes
         (analyst voice), duplicates inside a document, empty fields, items per document.
Layer B (sample): a DIFFERENT model family (Gemini flash-lite, separate concall-lane key only) re-reads each sampled fact with the surrounding transcript
         text and says: is the statement supported by the quote (yes/partial/no) and is the speaker management (mgmt/analyst/unclear).
Output: store/concall_audit/audit_<day>.json (every judged item) and a printed summary table per reader. Env: PER_GROUP (default 90), DOCS_PER_GROUP (15)."""
import os, sys, re, json, glob, time, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import concall_extract as CE
import concall_themes as CT

GK = os.environ.get("GEMINI_API_KEY_CONCALL", "").strip()
PER = int(os.environ.get("PER_GROUP", "90")); DOCS = int(os.environ.get("DOCS_PER_GROUP", "15"))
BUDGET = float(os.environ.get("BUDGET_MIN", "50")); T0 = time.time()
OUT = os.path.join(CE.store.ROOT, "concall_audit"); os.makedirs(OUT, exist_ok=True)
NUM = re.compile(r"\d[\d,]*\.?\d*")

def nums(s): return {n.replace(",", "").rstrip(".") for n in NUM.findall(s or "")}

def group(r):
    m = str(r.get("model", "?")).split("/")[-1].replace("-latest", "")
    return f"{m} v{r.get('v', 1)}"

recs = []
for f in sorted(glob.glob(os.path.join(CE.store.ROOT, "concall_facts", "20*.jsonl"))):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if not r.get("skip") and r.get("items"): recs.append(r)
p("records with facts:", len(recs))

# ---------- Layer A ----------
A = collections.defaultdict(lambda: collections.Counter())
for r in recs:
    g = group(r); a = A[g]; a["docs"] += 1; a["items"] += len(r["items"])
    seen = set()
    for it in r["items"]:
        q = it.get("quote") or ""; v = str(it.get("value") or ""); st = it.get("statement") or ""
        if v and nums(v) and not nums(v) <= nums(q): a["value_not_in_quote"] += 1
        st2 = re.sub(r"\b(FY|CY|H|Q)\s?-?\d{1,4}\b|\b(19|20)\d\d\b|\b\d{1,2}(st|nd|rd|th)\b", " ", st)
        qn = q.replace(",", "")
        if any(n.strip(".,").replace(",", "") not in qn for n in re.findall(r"\d[\d.,]*", st2) if len(n.strip(".,")) >= 2): a["stmt_num_not_in_quote"] += 1
        if q.count("?") >= 1: a["quote_has_question"] += 1
        if len(q) < 40: a["short_quote"] += 1
        if not it.get("period") and it.get("cat") in ("guidance", "capex", "order_book"): a["no_period_on_forward_cat"] += 1
        k = q[:60].lower()
        if k in seen: a["duplicate_quote"] += 1
        seen.add(k)
        if it.get("realigned"): a["realigned"] += 1
        if it.get("flag"): a["flagged"] += 1
p("=== LAYER A: structural checks (all stored facts) ===")
cols = ["docs", "items", "value_not_in_quote", "stmt_num_not_in_quote", "quote_has_question", "short_quote", "no_period_on_forward_cat", "duplicate_quote", "realigned", "flagged"]
p("group | " + " | ".join(cols))
for g, a in sorted(A.items(), key=lambda x: -x[1]["items"]):
    if a["docs"] >= 20:
        p(g + " | " + " | ".join(f"{a[c]}" if c in ("docs", "items") else f"{a[c]} ({a[c]/max(a['items'],1):.1%})" for c in cols))

# ---------- Layer B ----------
JP = """You audit facts extracted from an Indian company's earnings call. For each numbered item you get the extracted STATEMENT (with value/period) and the QUOTE the extractor claims supports it, plus the transcript text around the quote (CONTEXT).
Return ONLY JSON: {"r":[{"i":<n>,"support":"yes|partial|no","speaker":"mgmt|analyst|unclear","note":"max 12 words"}]}
support = does the QUOTE alone fully justify the STATEMENT, VALUE and PERIOD? yes = exactly; partial = statement adds scope/units/timing/direction the quote does not state, or mixes things; no = contradicts or unsupported.
speaker = is the quote spoken by company management (mgmt) or by an analyst/question-asker (analyst); unclear if the context does not show.
Be strict. Do not use outside knowledge."""

def judge(batch):
    body = "".join(f"\n#{i}\nSTATEMENT: {b['statement']} | value={b.get('value')} | period={b.get('period')} | direction={b.get('direction')}\nQUOTE: {b['quote']}\nCONTEXT: {b['ctx']}\n" for i, b in enumerate(batch))
    for attempt in range(4):
        try:
            r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent", timeout=200,
                              headers={"x-goog-api-key": GK, "Content-Type": "application/json"},
                              json={"contents": [{"parts": [{"text": JP + "\n" + body}]}],
                                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 6000}})
            if r.status_code in (429, 500, 503):
                if r.status_code == 429 and "PerDay" in r.text: return "daily"
                time.sleep(10 * (attempt + 1)); continue
            if r.status_code != 200: return None
            m = re.search(r"\{.*\}", r.json()["candidates"][0]["content"]["parts"][0].get("text", ""), re.S)
            return {x["i"]: x for x in json.loads(m.group(0))["r"]}
        except Exception:
            time.sleep(6)
    return None

def ctx_for(text, quote):
    # whitespace-insensitive match (PDF text has breaks such as "lookin g")
    idx = [i for i, ch in enumerate(text) if not ch.isspace()]
    comp = "".join(text[i] for i in idx).lower()
    k = re.sub(r"\s+", "", quote)[:45].lower()
    j = comp.find(k)
    if j < 0: return None
    i = idx[j]
    return text[max(0, i - 500): i + len(quote) + 300].replace("\n", " ")

if not GK:
    p("no GEMINI_API_KEY_CONCALL - Layer B skipped"); publish(); sys.exit(0)

rnd = random.Random(int(time.time()) // 86400)
by_g = collections.defaultdict(list)
for r in recs: by_g[group(r)].append(r)
judged = []
NOCTX = collections.Counter()
for g, rs in sorted(by_g.items(), key=lambda x: -len(x[1])):
    if len(rs) < 20: continue
    rnd.shuffle(rs); picked = []
    for r in rs[:DOCS]:
        if (time.time() - T0) / 60 > BUDGET: break
        try: txt = CE.prep(CT.pdf_text(r["src"]) or "")
        except Exception: continue
        its = r["items"][:]; rnd.shuffle(its)
        for it in its[: max(1, PER // DOCS)]:
            c = ctx_for(txt, it["quote"])
            if not c:
                NOCTX[g] += 1; continue
            picked.append({**it, "ctx": c, "name": r["name"], "day": r["day"], "key": r["key"], "group": g})
    for k in range(0, len(picked), 12):
        if (time.time() - T0) / 60 > BUDGET: break
        res = judge(picked[k:k + 12])
        if res == "daily": p("Gemini daily limit reached on concall key - stopping"); break
        if not res: continue
        for i, b in enumerate(picked[k:k + 12]):
            x = res.get(i) or res.get(str(i))
            if x: judged.append({**{kk: b[kk] for kk in ("group", "name", "day", "key", "cat", "statement", "value", "period", "direction", "quote")}, "support": x.get("support"), "speaker": x.get("speaker"), "note": x.get("note"), "flag": b.get("flag"), "realigned": b.get("realigned")})
        time.sleep(4)
    p("judged so far:", len(judged), "| minutes", round((time.time() - T0) / 60))
day = time.strftime("%Y-%m-%d")
json.dump(judged, open(os.path.join(OUT, f"audit_{day}.json"), "w", encoding="utf-8"), ensure_ascii=False)
p("=== LAYER B: independent judge (Gemini flash-lite) on a sample ===")
p("group | n | support yes | partial | no | speaker analyst | unclear")
for g in sorted({j["group"] for j in judged}):
    js = [j for j in judged if j["group"] == g]; n = len(js)
    c = collections.Counter(j["support"] for j in js); s = collections.Counter(j["speaker"] for j in js)
    p(f"{g} (quote not found in transcript text, skipped: {NOCTX[g]}) | {n} | {c['yes']/n:.0%} | {c['partial']/n:.0%} | {c['no']/n:.0%} | {s['analyst']/n:.0%} | {s['unclear']/n:.0%}")
publish()
