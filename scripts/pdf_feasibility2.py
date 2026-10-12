"""Feasibility v2: PyMuPDF text + OCR for scanned pages; per-metric hits and miss diagnostics. Truth = BSE table."""
import os, re, subprocess, tempfile, time, random
from datetime import datetime
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

DAYS = [datetime(2026, 8, d) for d in (4, 6, 7, 11, 12, 13, 14)]
PER_DAY = int(os.environ.get("PER_DAY", "22"))
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "30"))
OCR_MAX_PAGES = 8
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
NUM = re.compile(r"\(?-?\d[\d,]*\.?\d*\)?")
SCALES = {"Rs million": 1.0, "Rs lakh": 10.0, "Rs crore": 0.1, "Rs thousand": 1000.0, "Rs actual": 1e6}

def nums(text):
    out = []
    for m in NUM.findall(text):
        s = m.strip("()-").replace(",", "")
        try:
            out.append(abs(float(s)))
        except ValueError:
            pass
    return out

def has(vals, target, loose=False):
    t = abs(target)
    tol = max(0.06 if loose else 0.011, 2e-4 * t)
    return any(abs(v - t) <= tol for v in vals)

def find(vals, target):
    """Return scale name where target appears (strict), else (loose), else None."""
    for loose in (False, True):
        for sname, k in SCALES.items():
            if has(vals, target * k, loose):
                return sname + ("~" if loose else "")
    return None

def pdf_text(content):
    import fitz
    doc = fitz.open(stream=content, filetype="pdf")
    pages = len(doc)
    txt, ocr_pages = "", 0
    for i, pg in enumerate(doc):
        if i >= 14:
            break
        t = pg.get_text() or ""
        if len(t.strip()) < 400 and ocr_pages < OCR_MAX_PAGES:
            try:
                pix = pg.get_pixmap(dpi=200)
                with tempfile.TemporaryDirectory() as td:
                    f = os.path.join(td, "p.png")
                    pix.save(f)
                    o = subprocess.run(["tesseract", f, "stdout", "--psm", "6"], capture_output=True, text=True, timeout=90).stdout
                t = t + "\n" + o
                ocr_pages += 1
            except Exception:
                pass
        txt += t + "\n"
    return pages, txt, ocr_pages

def main():
    t_end = time.time() + BUDGET_MIN * 60
    stats, rows, diag = {}, [], []
    def bump(k): stats[k] = stats.get(k, 0) + 1
    with BSE(download_folder="./") as bse:
        pool = []
        for d in DAYS:
            day, pg, tot = [], 1, 0
            while pg <= 40:
                data = bse.announcements(page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t:
                    break
                tot += len(t)
                day += [r for r in t if r.get("CATEGORYNAME") == "Result" and r.get("ATTACHMENTNAME")]
                if tot >= data.get("Table1", [{}])[0].get("ROWCNT", 0):
                    break
                pg += 1
            random.Random(7).shuffle(day)
            pool += day[:PER_DAY]
        p(f"sampled filings: {len(pool)}")
        for r in pool:
            if time.time() > t_end:
                p("time budget reached"); break
            code, name = str(r["SCRIP_CD"]), r["SLONGNAME"]
            head = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat(r["NEWS_DT"][:19])
            q = rf.expected_quarter(head, filed)
            if q is None:
                bump("no_quarter_in_headline"); continue
            truth = {}
            for basis in ("consolidated", "standalone"):
                m = rf.fetch(bse, code, name, basis, q)
                if m and m.get("revenue") is not None and m.get("pat") is not None:
                    truth[basis] = m
            if not truth:
                bump("no_bse_table"); continue
            try:
                content = b""
                for folder in ("AttachLive", "AttachHis"):
                    resp = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/" + r["ATTACHMENTNAME"], headers=UA, timeout=60)
                    if resp.content[:4] == b"%PDF":
                        content = resp.content; break
                if not content:
                    bump("download_not_pdf"); continue
                pages, txt, ocrp = pdf_text(content)
            except Exception as e:
                bump("pdf_error"); rows.append(f"{name[:24]:24} PDF_ERROR {repr(e)[:60]}"); continue
            vals = nums(txt)
            best = None
            for basis, m in truth.items():
                rs, ps = find(vals, m["revenue"]), find(vals, m["pat"])
                both = rs if (rs and ps and rs.rstrip("~") == ps.rstrip("~")) else None
                sc = (2 if both else (1 if (rs or ps) else 0))
                if best is None or sc > best[0]:
                    best = (sc, basis, rs, ps, m)
            sc, basis, rs, ps, m = best
            if ocrp: bump("ocr_used")
            if sc == 2:
                bump("match" + ("_ocr" if ocrp else "")); status = "MATCH"
            elif sc == 1:
                bump("partial"); status = "PARTIAL"
            else:
                bump("none"); status = "NONE"
            rows.append(f"{name[:24]:24} pg={pages} ch={len(txt.strip())} ocr={ocrp} {status} {basis[:4]} rev={rs} pat={ps}")
            if status != "MATCH" and len(diag) < 7:
                lines = [l.strip() for l in txt.splitlines() if re.search(r"revenue from op|total income|net profit|profit.{0,12}(after|for the)|^\s*total revenue", l, re.I)]
                diag.append(f"## {name[:30]} truth rev={m['revenue']} pat={m['pat']} (Rs mn) ch={len(txt.strip())} ocr={ocrp}\n" + "\n".join(x[:130] for x in lines[:8]))
    p("SUMMARY:", stats)
    n = sum(stats.get(k, 0) for k in ("match", "match_ocr", "partial", "none"))
    mt = stats.get("match", 0) + stats.get("match_ocr", 0)
    p(f"tested {n}: full match {mt} ({100 * mt / max(n, 1):.0f}%), partial {stats.get('partial', 0)}, none {stats.get('none', 0)}")
    for x in rows[:110]:
        p(x)
    for x in diag:
        p(x)

try:
    main()
except Exception as e:
    import traceback
    p("Caught error:", repr(e)[:300], traceback.format_exc()[-500:])
publish()
