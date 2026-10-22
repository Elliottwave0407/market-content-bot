"""Read-only: which concrete model does each '-latest' alias serve? (3 tiny calls per alias; the response carries modelVersion.)"""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BASE = "https://generativelanguage.googleapis.com/v1beta"
for m in ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash"):
    seen = []
    for i in range(2):
        try:
            r = requests.post(f"{BASE}/models/{m}:generateContent", headers={"x-goog-api-key": KEY},
                              json={"contents": [{"parts": [{"text": "Reply with the single word OK."}]}], "generationConfig": {"maxOutputTokens": 8, "temperature": 0}}, timeout=60)
            if r.status_code == 200:
                seen.append(r.json().get("modelVersion"))
            else:
                msg = ""
                try: msg = r.json().get("error", {}).get("message", "")[:160]
                except Exception: pass
                seen.append(f"HTTP {r.status_code} {msg}")
        except Exception as e:
            seen.append("err " + repr(e)[:60])
        time.sleep(2)
    p(m, "->", seen)
publish()
