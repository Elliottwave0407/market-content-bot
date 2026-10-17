"""Standalone test: download a concall audio file and transcribe it with Gemini (Files API)."""
import os, sys, time, json, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
URL = os.environ.get("AUDIO_URL", "").strip()
NAME = os.environ.get("AUDIO_NAME", "call").strip() or "call"
MODEL = os.environ.get("GEMINI_AUDIO_MODEL", "").strip() or "gemini-flash-latest"
B = "https://generativelanguage.googleapis.com"

def main():
    os.makedirs("out", exist_ok=True)
    path = f"out/{NAME}.mp3"
    r = requests.get(URL, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    p("download status", r.status_code, r.headers.get("content-type"), r.headers.get("content-length"))
    if r.status_code != 200:
        return
    n = 0
    with open(path, "wb") as f:
        for ch in r.iter_content(1 << 20):
            f.write(ch); n += len(ch)
            if n > 300 << 20:
                p("too large"); return
    p("downloaded MB", round(n / 1e6, 1))
    # resumable upload
    h = {"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": str(n), "X-Goog-Upload-Header-Content-Type": "audio/mpeg", "Content-Type": "application/json"}
    s = requests.post(f"{B}/upload/v1beta/files?key={KEY}", headers=h, data=json.dumps({"file": {"display_name": NAME}}), timeout=60)
    up = s.headers.get("X-Goog-Upload-URL")
    if not up:
        p("upload start failed", s.status_code, s.text[:200].replace(KEY, "***")); return
    with open(path, "rb") as f:
        u = requests.post(up, headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Length": str(n)}, data=f, timeout=600)
    info = u.json().get("file", {})
    p("uploaded", info.get("name"), info.get("state"))
    for _ in range(60):
        g = requests.get(f"{B}/v1beta/{info['name']}?key={KEY}", timeout=30).json()
        if g.get("state") == "ACTIVE":
            break
        time.sleep(5)
    p("file state", g.get("state"), g.get("videoMetadata", {}))
    prompt = ("Transcribe this Indian company earnings call recording verbatim in English. Label each speaker (e.g. 'Management:', 'Analyst:') and use names if they are said. "
              "Keep every number exactly as spoken. Do not summarize. If audio is unclear write [inaudible].")
    body = {"contents": [{"parts": [{"file_data": {"mime_type": "audio/mpeg", "file_uri": g["uri"]}}, {"text": prompt}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 65000}}
    out = ""
    for attempt in range(4):
        rr = requests.post(f"{B}/v1beta/models/{MODEL}:generateContent?key={KEY}", json=body, timeout=900)
        if rr.status_code == 200:
            try:
                out = rr.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                p("bad response", rr.text[:200].replace(KEY, "***"))
            break
        p("gemini", rr.status_code, rr.text[:160].replace(KEY, "***"))
        time.sleep(15 * (attempt + 1))
    p("transcript chars", len(out), "words", len(out.split()))
    if out:
        open(f"out/{NAME}_transcript.txt", "w").write(out)
    try:
        requests.delete(f"{B}/v1beta/{info['name']}?key={KEY}", timeout=20)
    except Exception:
        pass
    os.remove(path)

main()
publish()
