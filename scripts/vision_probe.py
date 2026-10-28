"""Read-only probe: can a FREE NVIDIA NIM vision model read scanned result PDFs? Nothing is posted or stored.
Env DOCS = 'name:filename.pdf,...' (BSE AttachLive file names). Renders the first pages, asks each candidate VL model for the same JSON as the Gemini reader,
and prints the current-quarter column plus the arithmetic check. Key NVIDIA_API_KEY is never printed."""
import os, sys, re, json, time, base64, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import gemini_read as gr, pdf_card as pc, nse_results as nse
KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
T0 = time.time(); DEADLINE = float(os.environ.get("DEADLINE_MIN", "17")) * 60
try:
    ms = requests.get("https://integrate.api.nvidia.com/v1/models", headers=H, timeout=40).json().get("data", [])
    ids = [m["id"] for m in ms]
    cand = [i for i in ids if re.search(r"vision|[-/]vl|vila|neva|pixtral|gemma-3|phi-3.5|phi-4-multimodal|llama-4|qwen.*vl|paligemma|kosmos|fuyu|nemoretriever-ocr|ocr", i, re.I)]
    p("vision-like models on the free endpoint:", len(cand), cand[:40])
    want = os.environ.get("MODELS", "").strip()
    models = [m for m in want.split(",") if m] or cand[:4]
    import pymupdf
    for item in [x for x in os.environ.get("DOCS", "").split(",") if x]:
        if time.time() - T0 > DEADLINE: break
        name, fn = item.split(":")
        b = None
        for t in range(4):
            try:
                r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{fn}", headers=pc.UA, timeout=150)
                if r.content[:4] == b"%PDF": b = r.content; break
            except Exception as e:
                p("  download retry", name, type(e).__name__)
            time.sleep(5)
        if not b: p("DOWNLOAD FAILED", name); continue
        d = pymupdf.open(stream=b, filetype="pdf")
        p(f"== {name}: {len(b)//1024} KB, {len(d)} pages, text chars on pages 1-4: {[len(d[i].get_text()) for i in range(min(4, len(d)))]}")
        imgs = []
        pick = [i for i in range(min(8, len(d))) if len(d[i].get_text()) < 1500 and d[i].get_images()][:3] or list(range(min(3, len(d))))
        p("  pages rendered:", [i + 1 for i in pick], "text chars:", [len(d[i].get_text()) for i in pick])
        for i in pick:
            pix = d[i].get_pixmap(dpi=120)
            imgs.append(base64.b64encode(pix.tobytes("jpeg", jpg_quality=72)).decode())
        for m in models:
            if time.time() - T0 > DEADLINE: p("deadline reached, stopping"); break
            for pg, im in enumerate(imgs):
                if time.time() - T0 > DEADLINE: break
                body = {"model": m, "temperature": 0, "max_tokens": 1500, "messages": [{"role": "user", "content": [
                    {"type": "text", "text": gr.PROMPT + "\nIf this page does NOT contain the quarterly results statement table, return exactly {}."},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + im}}]}]}
                try:
                    r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=H, json=body, timeout=50)
                except Exception as e:
                    p(f"  {m} p{pg+1}: error {type(e).__name__}"); continue
                if r.status_code != 200:
                    p(f"  {m} p{pg+1}: HTTP {r.status_code} {r.text[:90]!r}"); 
                    if r.status_code in (400, 404, 422): break
                    time.sleep(3); continue
                txt = r.json()["choices"][0]["message"]["content"] or ""
                try:
                    out = gr._clean(json.loads(re.sub(r"^```json|```$", "", re.search(r"\{.*\}", txt, re.S).group(0).strip())))
                except Exception:
                    p(f"  {m} p{pg+1}: not JSON: {txt[:80]!r}"); continue
                if not out or not (out.get("standalone") or out.get("consolidated")):
                    continue
                for bs in ("consolidated", "standalone"):
                    dd = out.get(bs)
                    if isinstance(dd, dict):
                        ok = [nse.arith_col(dd, i) for i in range(3)]
                        p(f"  {m} p{pg+1} {bs} unit={out.get('unit')} arith={ok}: " + ", ".join(f"{k}={dd.get(k)}" for k in ("revenue", "other_income", "total_income", "total_expenses", "pbt", "tax", "pat", "eps")))
                break
            time.sleep(2.5)
except Exception:
    import traceback; p("ERROR", traceback.format_exc()[-700:])
publish()
