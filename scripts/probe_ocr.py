"""Read-only OCR feasibility test on a few image-only concall transcripts (free tesseract on the runner). Prints counts only."""
import os, io, json, glob, random, subprocess, tempfile, time, requests
from ci_out import p, publish
N = int(os.environ.get("N") or "8")
rows = []
for f in glob.glob("store/concall_facts/*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r.get("skip") == "short_or_scanned" and r.get("words", 0) >= int(os.environ.get("MINW") or "0") and r.get("words", 0) < int(os.environ.get("MAXW") or "250"): rows.append(r)
random.seed(7); random.shuffle(rows)
hdr = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
tot_pages = tot_words = ok = 0
for r in rows[:N]:
    t0 = time.time(); data = None
    for u in (r["src"], r["src"].replace("/AttachLive/", "/AttachHis/")):
        try:
            x = requests.get(u, headers=hdr, timeout=60)
            if x.status_code == 200 and len(x.content) > 2000: data = x.content; break
        except Exception: pass
    if not data: p(r["code"], r["day"], "download failed"); continue
    d = tempfile.mkdtemp(); open(d + "/a.pdf", "wb").write(data)
    try:
        info = subprocess.run(["pdfinfo", d + "/a.pdf"], capture_output=True, text=True).stdout
        pages = int([l for l in info.splitlines() if l.startswith("Pages:")][0].split()[1])
        subprocess.run(["pdftoppm", "-r", "150", "-gray", "-l", "60", "-png", d + "/a.pdf", d + "/pg"], check=True, timeout=600)
        words = 0
        for im in sorted(glob.glob(d + "/pg*.png")):
            o = subprocess.run(["tesseract", im, "-", "-l", "eng"], capture_output=True, text=True, timeout=120).stdout
            words += len(o.split())
        p(r["code"], r["day"], "pages", pages, "ocr_words", words, "was", r.get("words"), "sec", round(time.time() - t0), "KB", len(data) // 1024)
        tot_pages += min(pages, 60); tot_words += words; ok += words >= 1500
    except Exception as e:
        p(r["code"], r["day"], "ERR", type(e).__name__)
p("done: >=1500 words", ok, "of", N, "| pages", tot_pages, "| words", tot_words)
publish()
