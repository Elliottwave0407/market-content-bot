"""Strong-model judge, few big calls.
Stage A: per maker-call, ONE call per strong model containing the full text of up to 8 later earnings calls
         + that call's open promises. Quote is verified in code against the later transcripts.
Stage B: a different strong model audits only the evidence passages (batched, one call): does the passage itself
         show the outcome, stated by management? Anything weaker is downgraded to unverifiable.
Quota-aware: model ladder, per-day exhaustion detection, resumable (skips promises already judged by v3).
Writes verdicts into companydata/<SYM>/promises.json. Old cheap verdict kept as v2_label for comparison."""
import os, sys, re, json, time, traceback
from datetime import datetime
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import store
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E").strip().upper(); NOW = datetime.utcnow().strftime("%Y-%m-%d")
CNAME = os.environ.get("CNAME", SYM)
STRONG = ["gemini-flash-latest", "gemini-3.5-flash"]
DEAD = set(); USED = {}; ERR = []
def D(s): return datetime.strptime(s, "%d-%b-%Y")
def ask(model, prompt, timeout=300):
    """returns (json_or_None, status) status in ok|dead|retry|bad"""
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(3):
        try:
            r = requests.post(f"{BASE}/models/{model}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=timeout)
        except Exception as e:
            ERR.append(f"{model} exc {type(e).__name__}"); time.sleep(20); continue
        if r.status_code == 429:
            if "PerDay" in r.text:
                ERR.append(f"{model} PERDAY {re.sub(chr(10), ' ', r.text)[:160]}")
                DEAD.add(model); return None, "dead"
            ERR.append(f"{model} 429 {re.sub(chr(10), ' ', r.text)[:120]}")
            time.sleep(65); continue
        if r.status_code >= 500:
            ERR.append(f"{model} {r.status_code}"); time.sleep(20); continue
        if r.status_code != 200:
            ERR.append(f"{model} {r.status_code} {re.sub(chr(10), ' ', r.text)[:120]}")
            DEAD.add(model); return None, "dead"
        try:
            USED[model] = USED.get(model, 0) + 1
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", t.strip())), "ok"
        except Exception as e:
            ERR.append(f"{model} parse {type(e).__name__}"); return None, "bad"
    return None, "retry"
def alive(): return [m for m in STRONG if m not in DEAD]
def grams(t):
    n = norm(t); return {" ".join(n[i:i + 4]) for i in range(len(n) - 3)}
def good_quote(q): return bool(q) and "?" not in q and not re.search(r"\bquestion\b|\bif you\b|\bcould you\b|\bcan you\b", q, re.I)
JPROMPT = """Today is 18 Oct 2026. Company: {cname}. On {date} its management made the promises listed below (JSON). After this are the FILED QUARTERLY NUMBERS and the FULL TEXT of later earnings calls, each inside <call filed="DATE"> tags.
For each promise decide whether the later material directly shows the outcome. Rules:
- Use only statements by company management, or the filed numbers. Ignore analysts' questions and anything an analyst says.
- The quote must itself state or clearly show the outcome (done / done late / not done / abandoned). A passage that merely discusses the topic is NOT evidence.
- Judge timing against the promise date and the due date. "delayed" = done, but later than promised. "partly" = only part delivered.
- Copy the quote VERBATIM from one call (one or two sentences). Give that call's filed date.
- If the material does not directly show the outcome, answer "unverifiable". Never guess.
PROMISES: {promises}
FILED QUARTERLY NUMBERS (Rs Cr): {table}
{docs}
Return ONLY a JSON list, one object per promise: [{{"id":"","verdict":"delivered|delayed|missed|partly|unverifiable","source_filed":"DD-Mon-YYYY","quote":"","reason":"max 25 words"}}]"""
APROMPT = """You are auditing evidence for promises made by an Indian listed company's management. For each item, the PASSAGE was offered as proof of the VERDICT for the PROMISE (due: DEADLINE).
Answer "yes" only if the passage itself, stated by management (not an analyst, not a question), directly shows the outcome described by the verdict, including timing for "delayed". Answer "partly" if it only discusses the topic or shows part of it. Answer "no" if it does not support the verdict.
ITEMS: {items}
Return ONLY a JSON list: [{{"id":"","supports":"yes|partly|no","reason":"max 20 words"}}]"""
def clean(t): return re.sub(r"\s+", " ", t)
try:
    db = store.load(SYM, "promises.json"); Q = store.load(SYM, "quarters.json")["quarters"]
    order = sorted(db["calls"].items(), key=lambda kv: D(kv[1]["filed"]))
    texts = {u: clean(store.load_raw(SYM, c["key"]) or "") for u, c in order}
    G = {u: grams(texts[u]) for u, _ in order}
    tab = "; ".join(f"{l}: rev {round(q['revenue'],1)}, EBITDA% {round(100*q['ebitda']/q['revenue'],1)}, PAT {round(q['pat'],1)}" for l, q in sorted(Q.items(), key=lambda kv: datetime.strptime('01-' + kv[0], '%d-%b-%y'))[-10:])
    found = {}   # id -> (promise_obj, call, source_url, quote, verdict, reason)
    for n, (u, c) in enumerate(order):
        later = order[n + 1:n + 9]
        if not later: continue
        todo = []
        for x in c["promises"]:
            cc = (x.get("code_check") or {}).get("verdict")
            if cc and cc != "inconclusive": continue
            if (x.get("verdict") or {}).get("method", "").startswith("strong-context"): continue
            todo.append(x)
        if not todo: continue
        if not alive(): p("no strong model left; stopping at", c["filed"]); break
        docs = "\n".join(f'<call filed="{lc["filed"]}">\n{texts[lu]}\n</call>' for lu, lc in later)
        pl = json.dumps([{"id": x["id"], "promise": x["promise"], "due": x.get("deadline")} for x in todo])
        pr = JPROMPT.format(cname=CNAME, date=c["filed"], promises=pl, table=tab, docs=docs)
        j = None; used = None
        for m in alive():
            j, st = ask(m, pr)
            if isinstance(j, dict): j = j.get("results") or j.get("promises") or [j]
            if isinstance(j, list): used = m; break
            time.sleep(5)
        if not isinstance(j, list):
            p(c["filed"], "no answer for", len(todo), "promises"); continue
        byid = {str(e.get("id")): e for e in j if isinstance(e, dict)}
        p(c["filed"], "judge", used, "promises", len(todo), "answered", len(byid), "ctx_chars", len(docs))
        for x in todo:
            e = byid.get(x["id"], {})
            v = str(e.get("verdict") or "unverifiable").lower().split("|")[0].strip()
            q = e.get("quote") or ""; src_u = None
            if v != "unverifiable":
                if good_quote(q):
                    cands = [lu for lu, lc in later if quote_ok(q, G[lu])]
                    if cands:
                        claimed = str(e.get("source_filed") or "")
                        src_u = next((lu for lu in cands if dict(order)[lu]["filed"] == claimed), cands[0])
                if not src_u: v = "unverifiable"; q = ""
            found[x["id"]] = (x, c, src_u, q if v != "unverifiable" else "", v, e.get("reason"), used)
        time.sleep(15)
    # stage B: audit
    items = []
    for i, (x, c, src_u, q, v, rs, used) in found.items():
        if v == "unverifiable": continue
        t = texts[src_u]; k = t.find(q[:40]); k = max(0, k)
        ctx = t[max(0, k - 500): k + len(q) + 500]
        items.append({"id": i, "promise": x["promise"], "made_on": c["filed"], "deadline": x.get("deadline"), "verdict": v, "passage": ctx})
    aud = {}; audit_model = None
    if items:
        for m in (list(reversed(STRONG)) if len(STRONG) > 1 else STRONG):
            if m in DEAD: continue
            for s in range(0, len(items), 12):
                j, st = ask(m, APROMPT.format(items=json.dumps(items[s:s + 12])))
                if isinstance(j, dict): j = j.get("results") or [j]
                if isinstance(j, list):
                    for e in j:
                        if isinstance(e, dict): aud[str(e.get("id"))] = e
                    audit_model = m
                time.sleep(10)
            if aud: break
    tally = {}
    for i, (x, c, src_u, q, v, rs, used) in found.items():
        a = aud.get(i); label = v; note = None
        if v != "unverifiable":
            if a is None: label = "unverifiable (audit unavailable)"
            elif a.get("supports") == "yes": label = v
            elif a.get("supports") == "partly": label = "unverifiable (weak evidence)"
            else: label = "unverifiable (audit rejected)"
            note = a
        old = (x.get("verdict") or {})
        x["verdict"] = {"label": label, "method": "strong-context+audit", "evidence_quote": q if label == v else "", "source_filed": dict(order)[src_u]["filed"] if src_u else None,
                        "reason": rs, "judge_model": used, "audit_model": audit_model, "audit": note, "v2_label": old.get("label") if old.get("method") != "strong-context+audit" else old.get("v2_label"), "judged_on": NOW}
        tally[label] = tally.get(label, 0) + 1
        p(f"{c['filed']} | {label.upper()[:26]:26} | v2={str(x['verdict']['v2_label'])[:14]:14} | {x['promise'][:70]} | {q[:90]}")
    store.save(SYM, "promises.json", db)
    p("TALLY", json.dumps(tally), "| calls:", json.dumps(USED), "| dead:", sorted(DEAD), "| errors:", ERR[:6])
except Exception:
    p("ERR", traceback.format_exc()[-900:])
publish()
