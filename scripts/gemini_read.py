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

def _unit(u):
    """'In Lacs', 'Rs. in Lakhs', 'Crores', 'INR Millions' ... -> lakh / crore / million / thousand / actual (unknown text is left as is)."""
    t = str(u or "").lower()
    for word, canon in (("lac", "lakh"), ("lakh", "lakh"), ("crore", "crore"), ("crs", "crore"), ("million", "million"), ("thousand", "thousand"), ("actual", "actual"), ("rupee", "actual")):
        if word in t: return canon
    return u

def _clean(out):
    if isinstance(out, dict):
        out["unit"] = _unit(out.get("unit"))
        for b in ("consolidated", "standalone"):
            d = out.get(b)
            if isinstance(d, dict):
                for k, v in list(d.items()):
                    if isinstance(v, list): d[k] = [_num(i) for i in v]
    return out

FALLBACK = [m.strip() for m in os.environ.get("GEMINI_FALLBACK", "gemini-flash-latest,gemini-2.5-flash-lite,gemini-2.5-flash").split(",") if m.strip()]
USAGE = {}      # key label -> {"ok": n, "429": n, "other": n}, this run (logged by pdf_card)
QUOTA = {"until": {}}      # model -> time until which it is skipped after a quota (429) answer

def _quota_kind(r):
    t = r.text or ""
    return "per-day" if "PerDay" in t else "per-minute" if "PerMinute" in t else "rate"

def _read_core(key, model, pdf_bytes, tries=4, timeout=180, prompt=None, qd=None, label="main"):
    """Free-tier quota is per model, so on a 429 the next model is tried straight away instead of waiting."""
    qd = QUOTA["until"] if qd is None else qd
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf_bytes).decode()}}, {"text": prompt or PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    last = None
    models = [model] + [m for m in FALLBACK if m != model]
    for i in range(tries):
        for m in models:
            if qd.get(m, 0) > time.time():
                last = last or f"HTTP 429 (skipped {m}, quota)"; continue
            try:
                r = requests.post(f"{BASE}/models/{m}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=timeout)
            except requests.RequestException as ex_:      # 5 Nov: a read timeout used to abort the whole chain (other models and keys never tried); now it counts as a busy answer and the next model is tried
                last = f"timeout on {m} ({type(ex_).__name__})"; continue
            _u = USAGE.setdefault(label, {"ok": 0, "429": 0, "other": 0})
            _u["ok" if r.status_code == 200 else "429" if r.status_code == 429 else "other"] += 1
            if r.status_code == 429:
                kind = _quota_kind(r)
                qd[m] = time.time() + (3600 if kind == "per-day" else 60)
                last = f"HTTP 429 ({kind}) on {m}"; continue
            if r.status_code >= 500:
                last = f"HTTP {r.status_code} on {m}"; continue
            if r.status_code == 404 and m != model:
                qd[m] = time.time() + 86400; continue
            if r.status_code != 200:
                return None, f"HTTP {r.status_code} {r.text[:150]}"
            try:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return _clean(json.loads(re.sub(r"^```json|```$", "", txt.strip()))), None
            except Exception as e:
                return None, f"parse {repr(e)[:80]}"
        if i < tries - 1:
            time.sleep(15 * (i + 1))
    return None, last


QUOTA_OV2 = {}
QUOTA_OV = {}      # quota memory for the overflow key (kept apart from the main key's)

def read_pdf(key, model, pdf_bytes, tries=4, timeout=180, prompt=None):
    """Main key first. If every model on it answered 429 (quota), the same read is tried once on the dedicated results key (GEMINI_API_KEY_RESULTS, own Google project),
    and only if that is out too, once on the overflow key (GEMINI_API_KEY_OVERFLOW = the concall judge's project, last resort so the judge keeps its quota).
    Unset keys are skipped; without either this behaves exactly as before."""
    out, err = _read_core(key, model, pdf_bytes, tries, timeout, prompt)
    if out is not None or not (err and any(t in err for t in ("429", "HTTP 5", "timeout"))):
        return out, err      # a quota, busy (5xx) or timeout answer moves on to the next key; real errors stop here
    chain = []
    rk = os.environ.get("GEMINI_API_KEY_RESULTS", "").strip()
    ov = os.environ.get("GEMINI_API_KEY_OVERFLOW", "").strip()
    if rk and rk != key: chain.append((rk, QUOTA_OV2, "results-key"))
    if ov and ov not in (key, rk): chain.append((ov, QUOTA_OV, "concall-key"))
    for k2, qd2, lab in chain:
        o2, e2 = _read_core(k2, model, pdf_bytes, 1, timeout, prompt, qd=qd2, label=lab)
        if o2 is not None:
            return o2, None
        err = (err + f" | {lab}: " + str(e2))[:360]
        if not any(t in str(e2) for t in ("429", "HTTP 5", "timeout")):
            break
    return None, err
