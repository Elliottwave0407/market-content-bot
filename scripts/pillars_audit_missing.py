"""Audit only the pillar facts that were never audited (audit is None). One call on a strong model, then move
confirmed facts into pillars.json 'facts'. No re-extraction. Quota: 1 request."""
import os, sys, re, json, time, hashlib, traceback
from datetime import datetime
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import store
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E").strip().upper()
MODELS = os.environ.get("MODELS", "gemini-3.5-flash,gemini-flash-latest").split(",")
def D(s): return datetime.strptime(s, "%d-%b-%Y")
def clean(t): return re.sub(r"\s+", " ", t or "")
APROMPT = """You are auditing facts extracted about an Indian listed company. For each item the PASSAGE was offered as proof of the CLAIM.
Answer "yes" only if the passage itself, stated by management or the company's presentation (not an analyst, not a question), directly states the claim including any number. "partly" if it only discusses the topic or the number differs. "no" otherwise.
ITEMS: {items}
Return ONLY a JSON list with one object for EVERY item id: [{{"id":"","supports":"yes|partly|no","reason":"max 20 words"}}]"""
def ask(model, prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(3):
        try: r = requests.post(f"{BASE}/models/{model}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=300)
        except Exception as e: p("exc", type(e).__name__); time.sleep(20); continue
        if r.status_code == 429:
            if "PerDay" in r.text: p(model, "PERDAY"); return None
            time.sleep(65); continue
        if r.status_code >= 500: time.sleep(20); continue
        if r.status_code != 200: p(model, r.status_code); return None
        try: return json.loads(re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()))
        except Exception as e: p("parse", type(e).__name__); return None
    return None
try:
    P = store.load(SYM, "pillars.json")
    todo = [f for f in P["rejected"] if f.get("audit") is None]
    p("unaudited facts:", len(todo))
    if todo:
        meta = store.load(SYM, "transcripts.json")["items"]
        calls = sorted([t for t in meta if not t.get("dup_of")], key=lambda t: D(t["filed"]))[-3:]
        parts = []
        for t in calls:
            k = t.get("key") or hashlib.md5(t["url"].encode()).hexdigest()[:12]; parts.append(clean(store.load_raw(SYM, k) or ""))
        F = store.load(SYM, "filings.json")["items"]
        for f in sorted([f for f in F if f["desc"] == "Investor Presentation" and f.get("file")], key=lambda f: D(f["date"]))[-2:]:
            parts.append(clean(store.load_raw(SYM, "pres-" + hashlib.md5(f["file"].encode()).hexdigest()[:10]) or "")[:120000])
        alltext = " ".join(parts)
        items = []
        for i, f in enumerate(todo):
            o = f["fact"]; q = o.get("quote") or ""; k = max(0, alltext.find(q[:40]))
            claim = {kk: vv for kk, vv in o.items() if kk != "quote"}
            items.append({"id": str(i), "claim": f["path"].strip("/") + ": " + json.dumps(claim), "passage": alltext[max(0, k - 450): k + len(q) + 450]})
        aud = {}; used = None
        for m in MODELS:
            j = ask(m, APROMPT.format(items=json.dumps(items)))
            if isinstance(j, dict): j = j.get("results") or [j]
            if isinstance(j, list):
                aud = {str(e.get("id")): e for e in j if isinstance(e, dict)}; used = m
                if aud: break
        p("audited by", used, "answers", len(aud), "of", len(todo))
        keep = []; still = []
        for i, f in enumerate(todo):
            a = aud.get(str(i)); f["audit"] = a
            (keep if a and a.get("supports") == "yes" else still).append(f)
            p(" ", "+" if a and a.get("supports") == "yes" else "-", f["path"], "|", (a or {}).get("supports"), "|", ((a or {}).get("reason") or "")[:90], "|", f["fact"].get("quote", "")[:70])
        P["facts"] += [{"path": f["path"], "fact": f["fact"], "audit": f["audit"]} for f in keep]
        P["rejected"] = [f for f in P["rejected"] if f.get("audit") is not None or f in still]
        P["rejected"] = [f for f in P["rejected"] if f not in keep]
        P["audit_missing_model"] = used
        store.save(SYM, "pillars.json", P)
        p("facts now:", len(P["facts"]), "| rejected:", len(P["rejected"]))
except Exception:
    p("ERR", traceback.format_exc()[-900:])
publish()
