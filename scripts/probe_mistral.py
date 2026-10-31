import os, requests
from ci_out import p, publish
k = os.environ.get("MISTRAL_API_KEY", "").strip(); p("key present", bool(k), "len", len(k))
for m in ("ministral-14b-latest", "mistral-small-latest"):
    r = requests.post("https://api.mistral.ai/v1/chat/completions", headers={"Authorization": "Bearer " + k, "Content-Type": "application/json"}, json={"model": m, "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 5}, timeout=60)
    p(m, r.status_code, r.text[:200], {a: b for a, b in r.headers.items() if "ratelimit" in a.lower() or "retry" in a.lower()})
publish()
