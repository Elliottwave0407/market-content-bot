"""Read-only: print every parsed row (label + numbers) of chosen pages of one PDF, text layer only. env URL, PAGES (comma list, 1-based; empty = all)."""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_read as rr
b = requests.get(os.environ["URL"], headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}, timeout=90).content
want = {int(p) for p in os.environ.get("PAGES", "").split(",") if p.strip()}
for i, (txt, rws) in enumerate(rr._pdf_rows(b, max_pages=20, ocr=os.environ.get("OCR") == "1"), 1):
    if want and i not in want: continue
    print(f"--- page {i} rows={len(rws)}")
    for r in rws:
        lb, nums = rr.split_row(r)
        print("   ", repr(lb[:90]), nums)
