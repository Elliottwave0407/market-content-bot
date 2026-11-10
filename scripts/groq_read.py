"""Second free TEXT reader for result filings (Groq, OpenAI-compatible). Same contract as nim_read.read_pdf: returns (json, None) or (None, reason).
Same safety: output rejected when any number is not found word for word in the filing text (nim_read.unsupported). The arithmetic gate runs afterwards in pdf_card, as for every reader.
Small requests only (free tier caps the size of one request): the caller passes the trimmed PDF (results pages)."""
import os, re, json, time, requests
import gemini_read as gr
import nim_read as nr

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_RESULT_MODEL", "openai/gpt-oss-120b")
LIMIT = int(os.environ.get("GROQ_TEXT_LIMIT", "12000"))

def key():
    return os.environ.get("GROQ_API_KEY", "").strip()

def read_pdf(pdf_bytes, prompt=None, timeout=60):
    k = key()
    if not k:
        return None, "groq: no key"
    try:
        txt = nr.pdf_text(pdf_bytes, limit=LIMIT)
    except Exception as e:
        return None, f"groq: text extract failed {repr(e)[:60]}"
    if len(re.sub(r"\W", "", txt)) < 400:
        return None, "groq: no text layer (scanned)"
    msg = (prompt or gr.PROMPT) + "\n\nThe filing text follows (tables are shown with | between cells).\n\n" + txt
    last = None
    for att in range(4):
        try:
            r = requests.post(URL, headers={"Authorization": "Bearer " + k, "Content-Type": "application/json"}, timeout=timeout,
                              json={"model": MODEL, "messages": [{"role": "user", "content": msg}], "max_tokens": 4000, "temperature": 0, "response_format": {"type": "json_object"}})
        except Exception as e:
            last = f"groq: {type(e).__name__}"; time.sleep(3); continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"groq: HTTP {r.status_code}"; time.sleep(5 * (att + 1)); continue
        if r.status_code == 413 and len(txt) > 3000:      # request over the free per-minute token cap: retry with less text (results pages come first); numbers are still checked against the text that was sent
            txt = txt[: len(txt) * 55 // 100]
            msg = (prompt or gr.PROMPT) + "\n\nThe filing text follows (tables are shown with | between cells).\n\n" + txt
            last = "groq: HTTP 413"; continue
        if r.status_code != 200:
            return None, f"groq: HTTP {r.status_code} {r.text[:80]}"
        try:
            j = gr._clean(json.loads(r.json()["choices"][0]["message"]["content"]))
        except Exception as e:
            return None, f"groq: parse {repr(e)[:50]}"
        bad = nr.unsupported(j, txt)
        if bad:
            return None, f"groq: {bad} numbers not found in the filing text (possible invention): rejected"
        return j, None
    return None, last or "groq: failed"
