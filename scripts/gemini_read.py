"""Read a results PDF with a Gemini vision model -> numbers (JSON). Key via env GEMINI_API_KEY (header, never printed)."""
import base64, json, os, re, time
import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
PROMPT = """You are reading an Indian listed company's quarterly financial results filing (PDF, may be scanned).
Extract the 'Statement of Unaudited/Audited Financial Results' table. Return ONLY JSON:
{"unit":"lakh|crore|million|thousand|actual",
 "quarter_end_columns":["<current quarter end date>","<previous quarter end date>","<year-ago quarter end date>"],
 "consolidated": {"revenue":[c,p,y],"other_income":[c,p,y],"total_income":[c,p,y],"total_expenses":[c,p,y],"finance_costs":[c,p,y],"depreciation":[c,p,y],"pbt":[c,p,y],"tax":[c,p,y],"pat":[c,p,y],"eps":[c,p,y]} or null,
 "standalone": {same keys} or null}
Rules: c = current quarter, p = immediately preceding quarter, y = same quarter last year (the first three numeric columns; ignore half-year and full-year columns).
revenue = 'Revenue from operations' (total, incl. other operating income). pbt = profit before tax (after exceptional items). pat = net profit/(loss) for the period (before minority/attributable split, after tax).
Numbers exactly as printed, in the printed unit; negatives for losses. Use null for any value not present. Do not compute or guess."""

def list_models(key):
    r = requests.get(f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=30)
    r.raise_for_status()
    return [m["name"].split("/")[-1] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]

def _num(x):
    """The model sometimes returns figures as printed strings ('4,892.04', '(268.42)', '-'): make them numbers."""
    if isinstance(x, str):
        t = x.strip().replace(",", "").replace("\u2212", "-")
        neg = t.startswith("(") and t.endswith(")")
        t = t.strip("()").strip()
        if t in ("", "-", "--", "NA", "N.A.", "nil", "Nil", "null"): return None
        try: v = float(t)
        except ValueError: return x
        return -v if neg else v
    return x

def _clean(out):
    if isinstance(out, dict):
        for b in ("consolidated", "standalone"):
            d = out.get(b)
            if isinstance(d, dict):
                for k, v in list(d.items()):
                    if isinstance(v, list): d[k] = [_num(i) for i in v]
    return out

def read_pdf(key, model, pdf_bytes, tries=4, timeout=180, prompt=None):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf_bytes).decode()}}, {"text": prompt or PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    last = None
    for i in range(tries):
        r = requests.post(f"{BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=timeout)
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            time.sleep(15 * (i + 1)); continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} {r.text[:150]}"
        try:
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _clean(json.loads(re.sub(r"^```json|```$", "", txt.strip()))), None
        except Exception as e:
            return None, f"parse {repr(e)[:80]}"
    return None, last
