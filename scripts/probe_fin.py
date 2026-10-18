import os, sys, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
B = "https://generativelanguage.googleapis.com/v1beta"
for m in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"):
    try:
        r = requests.post(f"{B}/models/{m}:generateContent", headers={"x-goog-api-key": KEY}, json={"contents": [{"parts": [{"text": "Say OK"}]}]}, timeout=60)
        msg = ""
        try:
            e = r.json().get("error", {}); msg = e.get("message", "")[:260]
            det = [d for d in e.get("details", []) if "violations" in d]
            if det: msg += " | " + json.dumps([ (v.get("quotaMetric","")[-60:], v.get("quotaId","")[-50:]) for v in det[0]["violations"]])[:300]
        except Exception: msg = r.text[:200]
        p(m, r.status_code, msg.replace("\n", " "))
    except Exception as ex:
        p(m, "err", repr(ex)[:80])
publish()
