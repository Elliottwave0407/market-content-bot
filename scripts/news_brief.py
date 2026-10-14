"""Turn a filing's text into a short card brief (headline, key-figure line, bullets).
Gemini Flash-Lite (free tier, text only, 1 call per card). Every number in the answer must appear in the source text,
otherwise the answer is discarded and a rule-based fallback is used. Never invents figures."""
import json, os, re
import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-flash-lite-latest"
PROMPT = """You write a short brief for an Indian stock-market news card from a company's exchange filing text.
Return ONLY JSON: {"headline":"<=70 chars, plain, punchy, no hype, no emojis","sub":"<=90 chars: the single most important fact WITH its number (amount, quantity, rating, date, %) or null if the text has no number","bullets":["3 to 5 bullets, each <=95 chars, one fact each"]}
Rules: use ONLY facts stated in the text. Do not add numbers, names or opinions. Keep numbers exactly as written (units included, e.g. Rs 245 crore). No advice, no predictions. Bullets cover who/what, value, timeline/conditions, counterparty, any next step - only if present.
Category: @TAG | Company: @CO
Filing title: @TITLE
Filing text:
@TEXT"""

def _nums(s):
    return set(re.sub(r"[,\s]", "", m) for m in re.findall(r"\d[\d,]*\.?\d*", s or ""))

def _ok(out, source):
    if not isinstance(out, dict) or not out.get("headline") or not isinstance(out.get("bullets"), list) or not out["bullets"]:
        return False
    src = _nums(source)
    blob = " ".join([out.get("headline") or "", out.get("sub") or ""] + [str(b) for b in out["bullets"]])
    for n in _nums(blob):
        n = n.rstrip(".")
        if n and n not in src and not any(n in s for s in src if len(n) >= 3):
            return False
    return True

def fallback(title, detail):
    """Rule-based: sentences of the filing text as bullets."""
    txt = re.sub(r"\s+", " ", detail or "").strip()
    sents = [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", txt) if len(s.strip()) > 25][:4]
    bl = []
    for s in sents:
        s = s.rstrip(".;")
        bl.append(s if len(s) <= 110 else s[:107].rsplit(" ", 1)[0] + "...")
    return {"headline": title, "sub": None, "bullets": bl}

def brief(tag, company, title, detail, key=None):
    key = key or os.environ.get("GEMINI_API_KEY", "").strip()
    src = f"{title}\n{detail or ''}"
    if not key or not detail or len(detail) < 60:
        return fallback(title, detail), "rule"
    try:
        prompt = PROMPT.replace("@TAG", tag).replace("@CO", company).replace("@TITLE", title).replace("@TEXT", (detail or "")[:3500])
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=40)
        if r.status_code != 200:
            return fallback(title, detail), f"rule (HTTP {r.status_code})"
        out = json.loads(re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()))
        if isinstance(out, list) and out:
            out = out[0]
        out["bullets"] = [str(b).strip() for b in out["bullets"] if str(b).strip()][:5]
        if _ok(out, src):
            return out, "gemini"
        return fallback(title, detail), "rule (numbers not in source)"
    except Exception as e:
        return fallback(title, detail), "rule (" + repr(e)[:40] + ")"
