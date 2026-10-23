"""Read-only head-to-head: the nightly Gemini scan prompt vs the NVIDIA reader on the SAME transcripts. Saves both outputs to store/concall_compare/compare.json for review. Posts nothing."""
import os, sys, re, json, gzip, glob, time, ast
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
import concall_extract as CE

GK = os.environ.get("GEMINI_API_KEY", "").strip()
GM = os.environ.get("GEMINI_SCAN_MODEL", "").strip() or "gemini-flash-lite-latest"
N = int(os.environ.get("N_DOCS", "20"))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "concall_scan.py"), encoding="utf-8").read()
SCAN_PROMPT = next(n.value.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PROMPT")

def scan_call(text):
    body = {"contents": [{"parts": [{"text": SCAN_PROMPT + "\n\nTRANSCRIPT:\n" + text[:300000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(4):
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{GM}:generateContent", headers={"x-goog-api-key": GK}, json=body, timeout=300)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (i + 1)); continue
        if r.status_code != 200: return None
        try: return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception: return None
    return None

def scan_items(j):
    out = []
    def add(cat, d):
        if isinstance(d, dict) and d.get("quote"): out.append({"cat": cat, "statement": d.get("detail") or d.get("metric") or "", "quote": d["quote"]})
    for k in ("ebitda_margin", "margin_outlook", "rev_yoy_pct", "pat_yoy_pct", "order_book"):
        add(k, j.get(k))
    for k in ("guidance", "capex", "capacity", "mix", "moat", "catalysts", "risks"):
        for d in (j.get(k) or []): add(k, d)
    return out

docs = []
for f in sorted(glob.glob("store/concall_text/*.txt.gz")):
    t = gzip.open(f, "rt", errors="ignore").read()
    if len(t.split()) > 4000 and "moderator" in t.lower():
        docs.append((os.path.basename(f)[:-7], CE.prep(t)))
docs = docs[:N]
res = []
import traceback
def save():
    os.makedirs("store/concall_compare", exist_ok=True)
    json.dump(res, open("store/concall_compare/compare.json", "w"), ensure_ascii=False)
for name, t in docs:
    try:
        rec = {"doc": name, "words": len(t.split())}
        t0 = time.time(); j = scan_call(t) if GK else None; rec["scan_sec"] = round(time.time() - t0)
        if j:
            its = scan_items(j)
            ok = CE.verify([{"quote": i["quote"], "statement": i["statement"], "cat": i["cat"]} for i in its], t)
            rec["scan"] = {"one_line": j.get("one_line"), "not_said": j.get("not_said"), "n_raw": len(its), "n_exact": len(ok), "items": ok}
        t0 = time.time(); raw = []
        for ch in CE.chunks(t):
            g = CE.call(CE.MODELS[0], ch)
            raw += (g or {}).get("items") or []
        rec["reader_sec"] = round(time.time() - t0)
        ok2 = CE.verify(raw, t)
        rec["reader"] = {"n_raw": len(raw), "n_exact": len(ok2), "items": ok2}
        p(name, "scan raw/exact", rec.get("scan", {}).get("n_raw"), rec.get("scan", {}).get("n_exact"), "| reader raw/exact", len(raw), len(ok2), f"| {rec.get('scan_sec')}s/{rec['reader_sec']}s")
        res.append(rec); save()
    except Exception:
        p("ERROR on", name, traceback.format_exc()[-300:])
os.makedirs("store/concall_compare", exist_ok=True)
json.dump(res, open("store/concall_compare/compare.json", "w"), ensure_ascii=False)
publish()
