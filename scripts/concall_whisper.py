"""Standalone test: transcribe a concall recording with faster-whisper on the CI runner (no API, no quota)."""
import os, sys, time, requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish

URL = os.environ.get("AUDIO_URL", "").strip()
NAME = os.environ.get("AUDIO_NAME", "call").strip() or "call"
SIZE = os.environ.get("WHISPER_MODEL", "small").strip() or "small"
PROMPT = "Earnings conference call of an Indian listed company. Terms: crore, lakh, EBITDA, PAT, YoY, QoQ, GPU, Blackwell, B200, capex, sovereign AI, FY27, Q2 FY27."

def main():
    os.makedirs("out", exist_ok=True)
    path = f"out/{NAME}.mp3"
    r = requests.get(URL, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    p("download", r.status_code)
    if r.status_code != 200:
        return
    with open(path, "wb") as f:
        for ch in r.iter_content(1 << 20):
            f.write(ch)
    from faster_whisper import WhisperModel
    t0 = time.time()
    m = WhisperModel(SIZE, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    p("model loaded", SIZE, round(time.time() - t0), "s; cpus", os.cpu_count())
    t1 = time.time()
    segs, info = m.transcribe(path, language="en", beam_size=1, vad_filter=True, initial_prompt=PROMPT, condition_on_previous_text=False)
    p("audio duration min", round(info.duration / 60, 1))
    out = []
    for s in segs:
        out.append(s.text.strip())
    text = "\n".join(out)
    p("transcribe seconds", round(time.time() - t1), "words", len(text.split()))
    open(f"out/{NAME}_whisper_{SIZE}.txt", "w").write(text)
    os.remove(path)

main()
publish()
