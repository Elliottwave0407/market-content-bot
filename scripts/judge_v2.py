"""Cheap-model judge: retrieval of relevant sentences + two Flash-Lite models must agree + verbatim quote check.
Judges promises that code could not settle (no code_check, or inconclusive). Writes verdicts into promises.json."""
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
MODELS = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
DEAD = set(); USED = {}
STOP = set("a an the and or of to in on for with by at from is are was were be been will would should could can may might we our us it its this that these those as but not no have has had do does did so if then than into over under about out up per i you they their there here which who what when where how also very just more most some any all each both much many next last first one two".split())
def D(s): return datetime.strptime(s, "%d-%b-%Y")
def ctoks(t): return {w for w in norm(t) if w not in STOP and len(w) > 2}
def sentences(t): return [x.strip() for x in re.split(r"(?<=[.?!])\s+", t) if len(x.strip()) > 25]
def retrieve(promise, docs, k=7):
    pt = ctoks(promise); pn = set(re.findall(r"\d[\d,\.]*", promise))
    cand = []
    for filed, ss in docs:
        for i, s_ in enumerate(ss):
            st = ctoks(s_); ov = len(pt & st)
            if not ov: continue
            sc = ov / (len(pt) ** 0.5) + 1.5 * len(pn & set(re.findall(r"\d[\d,\.]*", s_)))
            cand.append((sc, filed, i))
    cand.sort(reverse=True); out = []; seen = set()
    for sc, filed, i in cand[:k]:
        ss = dict(docs)[filed]; txt = " ".join(ss[max(0, i - 1):i + 2])
        if (filed, i) in seen: continue
        seen.add((filed, i)); out.append((filed, txt))
    return out
def ask(model, prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(3):
        r = requests.post(f"{BASE}/models/{model}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=90)
        if r.status_code == 429:
            if "PerDay" in r.text: DEAD.add(model); return None
            time.sleep(15 * (i + 1)); continue
        if r.status_code >= 500: time.sleep(10); continue
        if r.status_code != 200: DEAD.add(model); return None
        try:
            USED[model] = USED.get(model, 0) + 1
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            j = json.loads(re.sub(r"^```json|```$", "", t.strip()))
            return j[0] if isinstance(j, list) and j else j
        except Exception: return None
    return None
PROMPT = """Today is 18 Oct 2026. On {date} management of an Indian company made this promise: "{promise}" (due: {deadline}).
FILED QUARTERLY NUMBERS (Rs Cr): {table}
EXCERPTS from LATER earnings calls (labelled by filing date):
{ex}
Question: do the excerpts (or the filed numbers) directly show the outcome? Judge timing against the promise date and due date.
Return ONLY JSON {{"verdict":"delivered|delayed|missed|partly|unverifiable","quote":"one sentence copied VERBATIM from the excerpts that shows the outcome, or empty","reason":"max 20 words"}}.
Use "unverifiable" unless an excerpt directly shows the outcome. "delayed" = done but later than promised."""
try:
    db = store.load(SYM, "promises.json"); Q = store.load(SYM, "quarters.json")["quarters"]
    tmeta = {t["url"]: t for t in store.load(SYM, "transcripts.json")["items"] if not t.get("dup_of")}
    order = sorted(db["calls"].items(), key=lambda kv: D(kv[1]["filed"]))
    texts = {u: store.load_raw(SYM, c["key"]) or "" for u, c in order}
    sents = {u: sentences(texts[u]) for u, _ in order}
    tab = "; ".join(f"{l}: rev {round(q['revenue'],1)}, EBITDA% {round(100*q['ebitda']/q['revenue'],1)}, PAT {round(q['pat'],1)}" for l, q in sorted(Q.items(), key=lambda kv: datetime.strptime('01-' + kv[0], '%d-%b-%y'))[-9:])
    tally = {}; n_done = 0
    for n, (u, c) in enumerate(order):
        later = [(order[m][1]["filed"], sents[order[m][0]]) for m in range(n + 1, min(n + 4, len(order)))]
        if not later: continue
        for x in c["promises"]:
            cc = (x.get("code_check") or {}).get("verdict")
            if cc and cc not in ("inconclusive",): continue
            if x.get("verdict") and x["verdict"].get("method") == "retrieval+consensus": continue
            ex = retrieve(x["promise"] + " " + str(x.get("deadline") or ""), later)
            if not ex: continue
            exs = "\n".join(f"[{f}] {t}" for f, t in ex); G = {" ".join(norm(exs)[i:i + 4]) for i in range(len(norm(exs)) - 3)}
            pr = PROMPT.format(date=c["filed"], promise=x["promise"], deadline=x.get("deadline"), table=tab, ex=exs)
            res = []
            for m in MODELS:
                if m in DEAD: continue
                j = ask(m, pr)
                if isinstance(j, dict):
                    v = str(j.get("verdict") or "unverifiable").lower().split("|")[0].strip()
                    q = j.get("quote") or ""
                    ok = bool(q) and quote_ok(q, G)
                    if v != "unverifiable" and not ok: v = "unverifiable"
                    res.append({"model": m, "verdict": v, "quote": q if ok else "", "reason": j.get("reason")})
                if len(res) == 2: break
                time.sleep(0.5)
            if len(res) < 2: label = "unjudged (models unavailable)"
            elif res[0]["verdict"] == res[1]["verdict"]: label = res[0]["verdict"]
            else: label = "unverifiable (models disagree)"
            best = next((r for r in res if r["verdict"] == label and r["quote"]), res[0] if res else {})
            x["verdict"] = {"label": label, "method": "retrieval+consensus", "evidence_quote": best.get("quote", ""), "reason": best.get("reason"), "votes": [{"model": r["model"], "verdict": r["verdict"]} for r in res], "judged_on": NOW}
            tally[label] = tally.get(label, 0) + 1; n_done += 1
            p(f"{c['filed']} | {label.upper()[:16]:16} | {x['promise'][:80]} | votes {[r['verdict'][:5] for r in res]} | {str(best.get('quote',''))[:100]}")
    store.save(SYM, "promises.json", db)
    p("TALLY", json.dumps(tally), "| calls:", json.dumps(USED), "| dead:", sorted(DEAD))
except Exception:
    p("ERR", traceback.format_exc()[-800:])
publish()
