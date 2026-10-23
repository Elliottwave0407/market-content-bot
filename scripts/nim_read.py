"""Backup reader for result PDFs when Gemini is out of quota / busy: text + tables are pulled from the (trimmed) PDF locally and a free NVIDIA NIM model returns the same JSON as the Gemini reader.
Every number it returns still goes through the same arithmetic, column-date and BSE-history checks as before. Scanned PDFs (no text layer) cannot be read here: return (None, reason). Key: env NVIDIA_API_KEY (never printed)."""
import os, re, json, time
import requests
import gemini_read as gr

URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELS = [m for m in os.environ.get("NIM_RESULT_MODELS", "deepseek-ai/deepseek-v4.1-flash,nvidia/nemotron-3-ultra-550b-a55b").split(",") if m]
DOWN = {"until": 0.0}

def key():
    return os.environ.get("NVIDIA_API_KEY", "").strip()

def pdf_text(b, limit=45000):
    import fitz
    d = fitz.open(stream=b, filetype="pdf")
    out = []
    for i, pg in enumerate(d):
        if i >= 8: break
        tabs = ""
        try:
            for t in pg.find_tables().tables:
                tabs += "\n".join(" | ".join((c or "").replace("\n", " ").strip() for c in r) for r in t.extract()) + "\n\n"
        except Exception:
            pass
        raw = pg.get_text("text")
        out.append((f"[PAGE {i+1} TABLES]\n{tabs}\n" if len(tabs) > 200 else "") + f"[PAGE {i+1} TEXT]\n{raw}")
    return "\n".join(out)[:limit]

BADL = []

def _nums(text):
    out = set()
    for t in re.findall(r"\(?-?\d[\d,]*\.?\d*\)?", text):
        try: out.add(round(abs(float(t.strip("()").replace(",", ""))), 2))
        except ValueError: pass
    return out

def unsupported(j, text):
    """Every number the model returned must be printed in the filing text. A model that invents plausible, self-consistent numbers passes arithmetic checks, so this is the guard against it."""
    have = _nums(text)
    bad = 0
    BADL.clear()
    for b in ("consolidated", "standalone"):
        d = j.get(b)
        if not isinstance(d, dict): continue
        for k, v in d.items():
            for x in (v if isinstance(v, list) else []):
                if isinstance(x, (int, float)) and not isinstance(x, bool) and round(abs(x), 2) not in have and round(abs(x), 2) != 0:
                    bad += 1; BADL.append((b[:4], k, x))
    return bad

def cur_unsupported(j, text, basis):
    """How many of the CURRENT column's headline numbers (revenue, pbt, tax, pat, eps) are not printed anywhere in the filing text."""
    d = j.get(basis)
    if not isinstance(d, dict): return None
    have = _nums(text); bad = 0
    for k in ("revenue", "pbt", "tax", "pat", "eps"):
        v = d.get(k)
        x = v[0] if isinstance(v, list) and v else None
        if isinstance(x, (int, float)) and not isinstance(x, bool) and round(abs(x), 2) != 0 and round(abs(x), 2) not in have:
            bad += 1
    return bad

def read_pdf(pdf_bytes, prompt=None, timeout=150):
    k = key()
    if not k:
        return None, "nim: no key"
    if time.time() < DOWN["until"]:
        return None, "nim: cooling down"
    try:
        txt = pdf_text(pdf_bytes)
    except Exception as e:
        return None, f"nim: text extract failed {repr(e)[:60]}"
    if len(re.sub(r"\W", "", txt)) < 400:
        return None, "nim: no text layer (scanned)"
    msg = (prompt or gr.PROMPT) + "\n\nThe filing text follows (tables are shown with | between cells).\n\n" + txt
    last, allr = None, []
    for m in MODELS:
        extra = {"thinking": False} if "deepseek" in m else {"enable_thinking": False}
        try:
            r = requests.post(URL, headers={"Authorization": "Bearer " + k}, timeout=timeout,
                              json={"model": m, "messages": [{"role": "user", "content": msg}], "max_tokens": 4000, "temperature": 0, "chat_template_kwargs": extra})
        except Exception as e:
            last = f"nim {m.split('/')[-1]}: {repr(e)[:50]}"; continue
        if r.status_code == 429:
            DOWN["until"] = time.time() + 20; last = "nim: 429"; allr.append(last); continue
        if r.status_code != 200:
            last = f"nim {m.split('/')[-1]}: HTTP {r.status_code}"; allr.append(last); continue
        try:
            s = re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"].get("content") or "", flags=re.S)
            j = gr._clean(json.loads(re.search(r"\{.*\}", s, re.S).group(0)))
        except Exception as e:
            last = f"nim {m.split('/')[-1]}: parse {repr(e)[:50]}"; allr.append(last); continue
        bad = unsupported(j, txt)
        if bad:
            last = f"nim {m.split('/')[-1]}: {bad} numbers not found in the filing text (possible invention): rejected e.g. {BADL[:5]}"; allr.append(last[:110]); continue
        return j, None
    return None, (" | ".join(allr) if allr else last)
