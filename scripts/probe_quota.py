"""Tiny probe: one 1-token-ish call per model; prints status and the quota error text (no secrets)."""
import os, re, json, requests
from ci_out import p, publish
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELS = [x for x in os.environ.get("MODELS", "").split(",") if x.strip()] or ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview", "gemini-pro-latest"]
for m in MODELS:
    try:
        r = requests.post(f"{BASE}/models/{m}:generateContent", headers={"x-goog-api-key": KEY},
                          json={"contents": [{"parts": [{"text": "Reply with the single word OK"}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 20}}, timeout=60)
        if r.status_code == 200:
            u = r.json().get("usageMetadata", {})
            p(m, "200 OK", "tokens", u.get("totalTokenCount"))
        else:
            msg = re.sub(r"\s+", " ", r.text)
            ids = re.findall(r"(Generate\w+|quotaId\W+\w+|quotaMetric\W+[\w./-]+|retryDelay\W+\w+)", msg)
            p(m, r.status_code, msg[:230], "|", ids[:4])
    except Exception as e:
        p(m, "EXC", type(e).__name__)
publish()
