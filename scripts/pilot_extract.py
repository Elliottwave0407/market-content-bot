"""E2E pilot step 2 (dry run): two-pass extraction from concall + investor presentation, quotes verified in code."""
import os, sys, re, io, json, time, traceback
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
a = src.index("KEY = "); b = src.index("DBG = []")
exec(src[a:b])                                   # KEY, MODEL, BASE, PROMPT
exec(src[src.index("def norm"):src.index("def mcaps")])   # norm, quote_ok, pdf_text, gem, sanitize
PRES = os.environ.get("PRES_URL", "https://www.bseindia.com/xml-data/corpfiling/AttachLive/99b94a78-41b2-407f-b337-363b911809e8.pdf")
CALL = os.path.join(os.path.dirname(__file__), "..", "pilot", "e2e_q2fy27_call.txt")
PTAB = """From this investor presentation text, return ONLY JSON: {"quarters":[{"label":"Q2 FY27","revenue_cr":number,"ebitda_cr":number,"ebitda_margin_pct":number,"pat_cr":number}],"customers_or_utilisation":[{"detail":"","quote":""}],"capex_or_gpu":[{"detail":"","quote":""}],"segments":[{"detail":"","quote":""}]}.
List every quarter shown in any table or chart (oldest to newest), converting Mn to Cr (1 Cr = 10 Mn). Quotes verbatim from the text, max 25 words. Use null when not shown."""
def g2(prompt, text):
    body = {"contents": [{"parts": [{"text": prompt + "\n\nTEXT:\n" + text[:300000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(4):
        r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=240)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (i + 1)); continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        try:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", t.strip())), None
        except Exception as e:
            return None, "parse " + repr(e)[:60]
    return None, "rate/5xx"
def grams(text):
    t = norm(text); return {" ".join(t[i:i + 4]) for i in range(len(t) - 3)}
def items(f):
    out = []
    for k in ("guidance", "capex", "capacity", "mix", "moat", "catalysts", "risks"):
        for x in f.get(k, []):
            out.append((k, (x.get("detail") or x.get("metric") or "")[:110], x.get("quote") or ""))
    for k in ("ebitda_margin", "margin_outlook", "order_book", "rev_yoy_pct", "pat_yoy_pct"):
        x = f.get(k)
        if x:
            out.append((k, json.dumps({kk: vv for kk, vv in x.items() if kk != "quote"})[:110], x.get("quote") or ""))
    return out
def run(label, text):
    G = grams(text); res = []
    for n in (1, 2):
        f, err = gem(text)
        if not f:
            p(label, "pass", n, "failed", err); continue
        f = sanitize(f); res.append(f)
        its = items(f)
        ok = [i for i in its if quote_ok(i[2], G)]
        p(f"-- {label} pass {n}: {len(ok)}/{len(its)} items verified | {f.get('one_line')}")
    if not res: return
    keys2 = [{(k, norm(d)[:3] and " ".join(norm(d)[:3])) for k, d, q in items(r) if quote_ok(q, G)} for r in res]
    p(f"== {label} VERIFIED ITEMS (pass-1; * = also found in pass-2)")
    for k, d, q in items(res[0]):
        if quote_ok(q, G):
            star = "*" if len(keys2) > 1 and (k, " ".join(norm(d)[:3])) in keys2[1] else " "
            p(f"{star}[{k}] {d} | \"{q[:140]}\"")
    p("not_said:", res[0].get("not_said"))
try:
    call = open(CALL).read()
    p("call chars", len(call))
    run("CONCALL", call)
    pt = pdf_text(PRES)
    p("presentation chars", len(pt or ""))
    if pt:
        f, err = g2(PTAB, pt)
        p("== PRESENTATION TABLE", err or "")
        if f:
            for q in f.get("quarters") or []:
                p(json.dumps(q))
            G = grams(pt)
            for k in ("customers_or_utilisation", "capex_or_gpu", "segments"):
                for x in (f.get(k) or []):
                    if isinstance(x, dict) and quote_ok(x.get("quote"), G):
                        p(f"[{k}] {x.get('detail')} | \"{(x.get('quote') or '')[:140]}\"")
        run("PRESENTATION", pt)
except Exception:
    p("ERR", traceback.format_exc()[-1200:])
publish()
