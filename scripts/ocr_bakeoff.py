"""Read-only OCR bake-off on one scanned results page: tesseract raw vs tesseract with table-line removal vs RapidOCR (free, ONNX). Env: URL, PAGE (1-based), prints text + seconds for each."""
import os, sys, time, io, requests, re
import fitz, numpy as np
from PIL import Image
url, page = os.environ["URL"], int(os.environ.get("PAGE", "3"))
c = requests.get(url, headers={"Referer": "https://www.nseindia.com/", "User-Agent": "Mozilla/5.0"}, timeout=90).content
d = fitz.open(stream=c, filetype="pdf"); pg = d[page - 1]
pix = pg.get_pixmap(dpi=300); img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
print("page", page, img.size, flush=True)
import pytesseract
t = time.time(); raw = pytesseract.image_to_string(img, config="--psm 6"); print(f"== TESS RAW {time.time()-t:.1f}s\n{raw[:1800]}", flush=True)
import cv2
a = np.array(img); bw = cv2.adaptiveThreshold(a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 15)
h = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1)))
v = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60)))
clean = cv2.bitwise_not(cv2.subtract(bw, cv2.bitwise_or(h, v)))
t = time.time(); cl = pytesseract.image_to_string(Image.fromarray(clean), config="--psm 6"); print(f"== TESS LINE-REMOVED {time.time()-t:.1f}s\n{cl[:1800]}", flush=True)
try:
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR(); t = time.time(); res, _ = eng(np.array(img.convert("RGB")))
    lines = {}
    for box, txt, conf in (res or []):
        y = int(np.mean([p[1] for p in box]) // 18); lines.setdefault(y, []).append((min(p[0] for p in box), txt))
    out = "\n".join("  ".join(t_ for _, t_ in sorted(v_)) for _, v_ in sorted(lines.items()))
    print(f"== RAPIDOCR {time.time()-t:.1f}s\n{out[:1800]}", flush=True)
except Exception as e:
    print("rapidocr error", repr(e)[:200], flush=True)
