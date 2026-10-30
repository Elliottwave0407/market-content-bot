import os, time, requests
from ci_out import p, publish
for m, extra in (("deepseek-ai/deepseek-v4.1-flash", {"thinking": False}), ("nvidia/nemotron-3-ultra-550b-a55b", {"enable_thinking": False})):
    t = time.time()
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + os.environ.get("NVIDIA_API_KEY", "")}, timeout=90,
                          json={"model": m, "messages": [{"role": "user", "content": "Reply with the word ok"}], "max_tokens": 10, "chat_template_kwargs": extra})
        p(m, r.status_code, round(time.time() - t, 1), "s", r.text[:150].replace("\n", " ") if r.status_code != 200 else "ok")
    except Exception as e:
        p(m, "EXC", type(e).__name__, round(time.time() - t, 1), "s")
publish()
