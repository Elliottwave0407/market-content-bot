"""Read-only debug: download one filing PDF from a URL and show what the rule reader (text, then OCR) finds. Posts nothing, writes no state.
Env: URL (pdf link), HINT (optional headline text)."""
import os, sys, re, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RULE_OCR"] = "1"
import rule_read as rr

url = os.environ["URL"]
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}, timeout=60)
print("download", r.status_code, len(r.content), flush=True)
b = r.content
for ocr in (False, True):
    try:
        pages = rr._pdf_rows(b, ocr=ocr)
    except Exception as e:
        print("ocr" if ocr else "text", "pdf_rows error", repr(e)[:120]); continue
    txt = " ".join(t for t, _ in pages)
    print("== ocr" if ocr else "== text", "pages", len(pages), "chars", len(re.sub(r"\W", "", txt)), flush=True)
    print("  mentions consolidated:", len(re.findall(r"consolidated", txt, re.I)), "standalone:", len(re.findall(r"standalone", txt, re.I)))
    for m in re.finditer(r"statement of (consolidated|standalone)[^\n]{0,80}", txt, re.I):
        print("  title:", m.group(0)[:110])
res, why = rr.read_pdf(b, os.environ.get("HINT", ""), None)
print("READ_PDF why:", why)
if res:
    for k in ("consolidated", "standalone"):
        d = res.get(k)
        print(k, "->", None if not d else {x: d.get(x) for x in ("revenue", "pat", "eps")})
    print("unit", res.get("unit"), "cols", res.get("quarter_end_columns"), "ocr", res.get("_ocr"))
