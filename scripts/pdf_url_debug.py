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

# page dump: show how the rule reader sees each page that mentions a results statement
if os.environ.get("DUMP", "1") == "1":
    for ocr in (False, True):
        try:
            pages = rr._pdf_rows(b, ocr=ocr)
        except Exception:
            continue
        for pno, (txt, rws) in enumerate(pages):
            if not re.search(r"revenue from operations|total income|profit before", txt, re.I):
                continue
            print(f"--- {'OCR' if ocr else 'TEXT'} page {pno + 1}: rows={len(rws)}", flush=True)
            for r_ in rws[:70]:
                lb, nums = rr.split_row(r_)
                print("   ", repr(lb[:60]), nums, flush=True)

# raw tokens of the profit / tax rows (OCR garble hunting)
for ocr in (True,):
    pages = rr._pdf_rows(b, ocr=ocr)
    for pno, (txt, rws) in enumerate(pages):
        for r_ in rws:
            t_ = " ".join(w[4] for w in r_)
            if re.search(r"profit for the period|total tax expense", t_, re.I):
                print("TOKENS p%d: %s" % (pno + 1, [w[4] for w in r_]), flush=True)
