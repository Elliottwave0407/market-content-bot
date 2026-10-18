"""Qualitative pillars (visibility, capex/capacity, product mix, moat, sector, risks): ONE strong-model extraction call
over the latest 3 earnings calls + latest 2 investor presentations, then ONE audit call by a different model.
Every fact needs a verbatim quote verified in code; audit must confirm. Writes companydata/<SYM>/pillars.json.
Quota use per company: 1 extraction + 1-2 audit calls. DRY=1 uses canned output for local tests."""
import os, sys, re, io, json, time, hashlib, traceback
from datetime import datetime
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import store
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E").strip().upper(); CNAME = os.environ.get("CNAME", SYM); NOW = datetime.utcnow().strftime("%Y-%m-%d")
DRY = os.environ.get("DRY") == "1"
STRONG = os.environ.get("MODELS", "gemini-flash-latest,gemini-3.5-flash").split(","); DEAD = set(); USED = {}; ERR = []
def D(s): return datetime.strptime(s, "%d-%b-%Y")
def clean(t): return re.sub(r"\s+", " ", t or "")
def grams(t):
    n = norm(t); return {" ".join(n[i:i + 4]) for i in range(len(n) - 3)}
def ask(model, prompt, timeout=300):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(3):
        try: r = requests.post(f"{BASE}/models/{model}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=timeout)
        except Exception as e: ERR.append(f"{model} exc {type(e).__name__}"); time.sleep(20); continue
        if r.status_code == 429:
            if "PerDay" in r.text:
                msg = " ".join(r.text.split()); ERR.append(f"{model} PERDAY {msg[150:330]}"); DEAD.add(model); return None
            time.sleep(65); continue
        if r.status_code >= 500: time.sleep(20); continue
        if r.status_code != 200: ERR.append(f"{model} {r.status_code}"); DEAD.add(model); return None
        try:
            USED[model] = USED.get(model, 0) + 1
            return json.loads(re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()))
        except Exception as e: ERR.append(f"{model} parse {type(e).__name__}"); return None
    return None
EPROMPT = """Today is 18 Oct 2026. Company: {cname}. Below are the FULL TEXT of its latest earnings calls and investor presentations, each in <doc kind=".." filed="DATE"> tags, and its filed quarterly numbers.
Extract ONLY facts stated by company management or shown in the presentation. Ignore analysts' questions and anything an analyst says. Never infer or add outside knowledge. If a fact is not stated, use null (or an empty list). Every item needs a "quote" copied VERBATIM (one or two sentences) from the documents.
Return ONLY this JSON:
{{"recurring_share_pct":{{"value":0,"quote":""}},
 "customer_concentration":{{"top_n":0,"share_pct":0,"quote":""}},
 "contracted_demand":{{"detail":"","quote":""}},
 "quantified_guidance":[{{"metric":"","detail":"","quote":""}}],
 "capex_plan":{{"amount_cr":0,"period":"","quote":""}},
 "capacity":{{"detail":"","utilization_pct":0,"quote":""}},
 "returns_disclosed":{{"detail":"","quote":""}},
 "segments":[{{"name":"","share_pct":0,"quote":""}}],
 "value_added":{{"detail":"","share_pct":0,"quote":""}},
 "segment_margin":{{"detail":"","quote":""}},
 "moat":[{{"barrier":"","quote":""}}],
 "long_term_targets":[{{"metric":"","value":"","by":"","quote":""}}],
 "sector":[{{"fact":"","quote":""}}],
 "risks":[{{"type":"concentration|regulatory|execution|funding|supply|competition","text":"","quote":""}}]}}
FILED QUARTERLY NUMBERS (Rs Cr): {table}
{docs}"""
APROMPT = """You are auditing facts extracted about an Indian listed company. For each item the PASSAGE was offered as proof of the CLAIM.
Answer "yes" only if the passage itself, stated by management or the company's presentation (not an analyst, not a question), directly states the claim including any number. "partly" if it only discusses the topic or the number differs. "no" otherwise.
ITEMS: {items}
Return ONLY a JSON list: [{{"id":"","supports":"yes|partly|no","reason":"max 20 words"}}]"""
def walk(o, path=""):
    """yield (path, dict) for every dict that has a quote"""
    if isinstance(o, dict):
        if "quote" in o: yield path, o
        for k, v in o.items():
            if k != "quote": yield from walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk(v, f"{path}[{i}]")
def empty(o):
    return not o or all((v in (None, "", 0) for k, v in o.items() if k != "quote")) if isinstance(o, dict) else not o
def good_quote(q): return bool(q) and "?" not in q and not re.search(r"\bquestion\b|\bif you\b|\bcould you\b|\bcan you\b", q, re.I)
try:
    meta = store.load(SYM, "transcripts.json")["items"]; Q = store.load(SYM, "quarters.json")["quarters"]
    calls = sorted([t for t in meta if not t.get("dup_of")], key=lambda t: D(t["filed"]))[-3:]
    F = store.load(SYM, "filings.json")["items"]
    pres = sorted([f for f in F if f["desc"] == "Investor Presentation" and f.get("file")], key=lambda f: D(f["date"]))[-2:]
    docs = []
    for t in calls:
        k = t.get("key") or hashlib.md5(t["url"].encode()).hexdigest()[:12]
        tx = store.load_raw(SYM, k) or ""
        if tx: docs.append(("call", t["filed"], clean(tx)))
    for f in pres:
        k = "pres-" + hashlib.md5(f["file"].encode()).hexdigest()[:10]
        tx = store.load_raw(SYM, k)
        if tx is None:
            try: tx = pdf_text(f["file"]) or ""
            except Exception as e: tx = ""; p("pdf fail", f["date"], type(e).__name__)
            if tx: store.save_raw(SYM, k, tx)
        if tx: docs.append(("presentation", f["date"], clean(tx)[:120000]))
    p("docs", [(k, d, len(t)) for k, d, t in docs])
    tab = "; ".join(f"{l}: rev {round(q['revenue'],1)}, EBITDA% {round(100*q['ebitda']/q['revenue'],1)}, PAT {round(q['pat'],1)}" for l, q in sorted(Q.items(), key=lambda kv: datetime.strptime('01-' + kv[0], '%d-%b-%y'))[-8:])
    G = set().union(*[grams(t) for _, _, t in docs]) if docs else set()
    if DRY:
        raw = json.loads(os.environ["DRY_JSON"]); model = "dry"
    else:
        raw = None; model = None
        for m in STRONG:
            if m in DEAD: continue
            pr = EPROMPT.format(cname=CNAME, table=tab, docs="\n".join(f'<doc kind="{k}" filed="{d}">\n{t}\n</doc>' for k, d, t in docs))
            raw = ask(m, pr); model = m
            if isinstance(raw, list) and raw: raw = raw[0]
            if isinstance(raw, dict): break
            raw = None
    if not isinstance(raw, dict): p("no extraction answer", ERR[:3]); raise SystemExit
    # verify quotes in code
    facts = []
    for path, o in walk(raw):
        if empty(o): continue
        q = o.get("quote") or ""
        if good_quote(q) and quote_ok(q, G): facts.append((path, o))
        else: p("dropped (quote not verified):", path, str(q)[:60])
    # audit by other model
    items = []
    alltext = " ".join(t for _, _, t in docs)
    for i, (path, o) in enumerate(facts):
        k = max(0, alltext.find((o["quote"] or "")[:40]))
        claim = {kk: vv for kk, vv in o.items() if kk != "quote"}
        items.append({"id": str(i), "claim": path.strip("/") + ": " + json.dumps(claim), "passage": alltext[max(0, k - 450): k + len(o["quote"]) + 450]})
    aud = {}
    if items and not DRY:
        for m in [x for x in STRONG if x != model] + [model]:
            if m in DEAD: continue
            for s in range(0, len(items), 15):
                j = ask(m, APROMPT.format(items=json.dumps(items[s:s + 15])))
                if isinstance(j, dict): j = j.get("results") or [j]
                if isinstance(j, list):
                    for e in j:
                        if isinstance(e, dict): aud[str(e.get("id"))] = e
                time.sleep(8)
            if aud: audit_model = m; break
    else: audit_model = "dry"
    kept = []; rej = []
    for i, (path, o) in enumerate(facts):
        a = aud.get(str(i)); ok = DRY or (a is not None and a.get("supports") == "yes")
        (kept if ok else rej).append({"path": path, "fact": o, "audit": a})
    out = {"extracted_on": NOW, "extract_model": model, "audit_model": audit_model if items else None, "docs": [(k, d) for k, d, _ in docs],
           "facts": kept, "rejected": rej, "n_extracted": len(facts)}
    store.save(SYM, "pillars.json", out)
    p("facts extracted (quote verified):", len(facts), "| audit-confirmed:", len(kept), "| rejected:", len(rej))
    for f in kept: p(" +", f["path"], "|", json.dumps({k: v for k, v in f["fact"].items() if k != "quote"})[:110], "|", f["fact"]["quote"][:80])
    for f in rej: p(" -", f["path"], "|", (f["audit"] or {}).get("supports"), "|", ((f["audit"] or {}).get("reason") or "no audit")[:80])
    p("calls:", json.dumps(USED), "| dead:", sorted(DEAD), "| errors:", ERR[:3])
except SystemExit: pass
except Exception:
    p("ERR", traceback.format_exc()[-900:])
publish()
