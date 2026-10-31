"""Read-only: how does the NVIDIA free endpoint limit us? (1) quick single call on candidate models under current load, (2) burst of 8 parallel calls on nemotron vs on the best alternative: 429 share and latency."""
import os, time, json, requests
from concurrent.futures import ThreadPoolExecutor
from ci_out import p, publish
KEY = os.environ.get("NVIDIA_API_KEY", ""); URL = "https://integrate.api.nvidia.com/v1/chat/completions"
H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
def call(m, n=60, timeout=60):
    t = time.time()
    try:
        r = requests.post(URL, headers=H, json={"model": m, "messages": [{"role": "user", "content": "Reply with the word OK and nothing else."}], "max_tokens": n, "temperature": 0}, timeout=timeout)
        rl = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or "retry" in k.lower()}
        return m, r.status_code, round(time.time() - t, 1), rl, (r.text[:90] if r.status_code != 200 else "")
    except Exception as e: return m, type(e).__name__, round(time.time() - t, 1), {}, ""
r = requests.get("https://integrate.api.nvidia.com/v1/models", headers=H, timeout=60); ids = sorted(m["id"] for m in r.json().get("data", []))
cands = [m for m in ids if any(k in m for k in ("llama-3.3-70b", "llama-3.1-70b", "llama-3.1-405b", "llama-3.1-8b", "mistral-nemo", "mistral-small", "qwen3", "qwen2.5", "gemma-3", "nemotron-3-nano", "nemotron-super", "nemotron-ultra", "deepseek-v3", "gpt-oss", "phi-4"))][:24]
p("candidates", len(cands), cands)
with ThreadPoolExecutor(6) as ex:
    for res in ex.map(call, cands + ["nvidia/nemotron-3-ultra-550b-a55b"]): p("single", *res)
alt = None
def burst(m, n=8):
    t = time.time()
    with ThreadPoolExecutor(n) as ex: rs = list(ex.map(lambda _: call(m, 40, 90), range(n)))
    codes = [x[1] for x in rs]; p("burst", m, "n", n, "codes", {c: codes.count(c) for c in set(codes)}, "median s", sorted(x[2] for x in rs)[n // 2], "wall", round(time.time() - t, 1))
burst("nvidia/nemotron-3-ultra-550b-a55b")
publish()
