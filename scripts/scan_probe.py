"""Read-only: does the new Gemini key (own project) read scanned result tables, and which variant is most accurate?
Variants: whole trimmed PDF vs one page rendered as an image at 200 dpi, on several models. Compares with figures read by hand from the filings. Nothing is posted or stored."""
import os, sys, re, json, time, base64, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import gemini_read as gr, pdf_card as pc, nse_results as nse
KEY = os.environ.get("GEMINI_API_KEY_RESULTS", "").strip()
TRUTH = {
 "SCILAL": {"standalone": {"revenue": [767, 786, 613], "other_income": [2035, 1995, 2143], "total_income": [2802, 2781, 2756], "total_expenses": [1229, 959, 2169], "pbt": [1573, 1822, 587], "tax": [398, 420, 168], "pat": [1175, 1402, 419], "eps": [0.25, 0.30, 0.09]}},
 "WELSPUN": {"consolidated": {"revenue": [1411.33, 12.75, 490.21], "other_income": [0.01, 0.40, 2.18], "total_income": [1411.34, 13.15, 492.39], "total_expenses": [242.56, 27.95, 33.15], "pbt": [1168.78, -14.80, 459.24], "tax": [292.83, 0.08, 110.06], "pat": [875.95, -14.88, 349.18], "eps": [23.97, -0.41, 9.55]}},
}
DOCS = [x.split(":") for x in os.environ.get("DOCS", "").split(",") if x]
def _auto():
    try:
        ms = requests.get(f"{gr.BASE}/models?pageSize=200", headers={"x-goog-api-key": KEY}, timeout=40).json().get("models", [])
        names = [m["name"].split("/")[-1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
        p("models this key can call:", [n for n in names if re.search(r"flash|pro", n) and not re.search(r"image|tts|live|audio|embed|robotics|computer|gemma", n)][:30])
        return names
    except Exception as e:
        p("model list failed", type(e).__name__); return []
_names = _auto()
_want = os.environ.get("MODELS", "").strip()
MODELS = [m for m in _want.split(",") if m] or [n for n in ("gemini-pro-latest", "gemini-flash-latest", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash") if n in _names][:3]
p("testing models:", MODELS)
def call(model, parts):
    # (list outputs are unwrapped by the caller)
    body = {"contents": [{"parts": parts + [{"text": gr.PROMPT}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    err = None
    for t in range(4):
        try:
            r = requests.post(f"{gr.BASE}/models/{model}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=110)
        except Exception as e:
            err = type(e).__name__; time.sleep(8); continue
        if r.status_code == 200:
            try: return gr._clean(json.loads(re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()))), None
            except Exception as e: return None, "parse " + repr(e)[:50]
        try: msg = r.json()["error"]["message"]
        except Exception: msg = r.text
        err = f"HTTP {r.status_code}: {re.sub(r'\s+', ' ', msg)[:170]}"
        if r.status_code in (403, 503, 429): time.sleep(12 * (t + 1)); continue
        break
    return None, err
def score(out, truth):
    ok = tot = 0
    for bs, cols in truth.items():
        d = (out or {}).get(bs) or {}
        for k, v in cols.items():
            for i, x in enumerate(v):
                tot += 1
                try: ok += abs(float(d.get(k)[i]) - x) < 0.006 + 0.0005 * abs(x)
                except Exception: pass
    return ok, tot
try:
    import pymupdf
    for name, fn in DOCS:
        b = None
        for t in range(4):
            try:
                r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{fn}", headers=pc.UA, timeout=150)
                if r.content[:4] == b"%PDF": b = r.content; break
            except Exception as e: p("  download retry", name, type(e).__name__)
            time.sleep(5)
        if not b: p("DOWNLOAD FAILED", name); continue
        d = pymupdf.open(stream=b, filetype="pdf")
        pick = [i for i in range(min(8, len(d))) if len(d[i].get_text()) < 1500 and d[i].get_images()][:4]
        p(f"== {name}: {len(b)//1024} KB, table-page candidates {[i+1 for i in pick]}")
        trimmed = pc.trim_pdf(b)
        variants = [("pdf", [{"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(trimmed).decode()}}])]
        allp = [i for i in range(min(8, len(d))) if d[i].get_images()][:4] or [0, 1, 2]
        variants.append((f"imgs {[i+1 for i in allp]}", [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(d[i].get_pixmap(dpi=150).tobytes("jpeg", jpg_quality=80)).decode()}} for i in allp]))
        for model in MODELS:
            for vn, parts in variants:
                out, err = call(model, parts)
                if out is None: p(f"  {model} | {vn}: {err}"); continue
                if isinstance(out, list): out = next((x for x in out if isinstance(x, dict)), {})
                line = f"  {model} | {vn}: unit={out.get('unit')}"
                for bs in ("consolidated", "standalone"):
                    dd = out.get(bs)
                    if isinstance(dd, dict):
                        line += f" | {bs} arith={[nse.arith_col(dd, i) for i in range(3)]}"
                if name in TRUTH: line += f" | matches vs hand-read: {score(out, TRUTH[name])}"
                p(line)
                time.sleep(2)
except Exception:
    import traceback; p("ERROR", traceback.format_exc()[-700:])
publish()
