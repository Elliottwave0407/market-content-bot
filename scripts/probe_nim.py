"""Read-only: which NVIDIA NIM free models can this key actually call? Lists models, then sends one tiny prompt to candidates and records status + latency. Never prints the key."""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests

KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
BASE = "https://integrate.api.nvidia.com/v1"
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
p("key present:", bool(KEY), "len>20:", len(KEY) > 20)
ids = []
try:
    r = requests.get(BASE + "/models", headers=H, timeout=40)
    p("list status", r.status_code)
    if r.status_code == 200:
        ids = [m.get("id") for m in r.json().get("data", [])]
        p("models listed:", len(ids))
        keys = ("deepseek", "nemotron", "llama-3.3", "llama-4", "qwen", "mistral", "gpt-oss", "kimi", "glm", "minimax", "gemma")
        p("candidates:", ", ".join(sorted(i for i in ids if any(k in i.lower() for k in keys)))[:3000])
except Exception as e:
    p("list error", repr(e)[:120])

cands = [i for i in ids if any(k in i.lower() for k in ("deepseek", "nemotron-3", "gpt-oss", "qwen3", "llama-3.3", "llama-4", "kimi", "mistral-large", "glm"))][:14]
for m in cands:
    t = time.time()
    try:
        r = requests.post(BASE + "/chat/completions", headers=H, timeout=90,
                          json={"model": m, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 8, "temperature": 0})
        msg = ""
        if r.status_code != 200:
            msg = r.text[:110].replace("\n", " ")
        else:
            msg = (r.json()["choices"][0]["message"].get("content") or "")[:20]
        p("TEST", m, r.status_code, f"{time.time()-t:.1f}s", msg)
    except Exception as e:
        p("TEST", m, "err", repr(e)[:80])
    time.sleep(2)
publish()
