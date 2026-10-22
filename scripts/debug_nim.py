"""Read-only: why do NIM models return no JSON? Prints finish_reason, field names, and head of output for one short prompt, with thinking variants."""
import os, sys, gzip, glob, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
K = os.environ.get("NVIDIA_API_KEY", "").strip()
f = sorted(glob.glob("store/concall_text/*.txt.gz"))[1]
t = gzip.open(f, "rt", errors="ignore").read()[:30000]
prompt = 'From this earnings-call text return ONLY JSON {"guidance":[{"statement":"..","quote":"EXACT sentence copied"}]} with max 3 items.\n\nTEXT:\n' + t
variants = [("nvidia/nemotron-3-ultra-550b-a55b", {}), ("nvidia/nemotron-3-ultra-550b-a55b", {"chat_template_kwargs": {"enable_thinking": False}}),
            ("nvidia/nemotron-3.5-lightning-30b-a3b", {}), ("nvidia/nemotron-3.5-lightning-30b-a3b", {"chat_template_kwargs": {"enable_thinking": False}}),
            ("deepseek-ai/deepseek-v4.1-flash", {}), ("deepseek-ai/deepseek-v4.1-flash", {"chat_template_kwargs": {"thinking": False}})]
for m, extra in variants:
    t0 = time.time()
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + K}, timeout=200,
                          json={"model": m, "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000, "temperature": 0, **extra})
        if r.status_code != 200:
            p("V", m.split("/")[-1], json.dumps(extra)[:40], r.status_code, r.text[:100].replace("\n", " ")); continue
        ch = r.json()["choices"][0]; msg = ch["message"]
        p("V", m.split("/")[-1], json.dumps(extra)[:40], "finish", ch.get("finish_reason"), "fields", [k for k, v in msg.items() if v], f"{time.time()-t0:.0f}s",
          "| content:", (msg.get("content") or "")[:160].replace("\n", " "), "| reasoning_len:", len(msg.get("reasoning_content") or msg.get("reasoning") or ""))
    except Exception as e:
        p("V", m.split("/")[-1], "err", repr(e)[:80])
publish()
