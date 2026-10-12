"""Feasibility test: can result numbers be found in the filing PDFs? Ground truth = BSE structured table (past quarter)."""
import io, os, re, sys, time, random
from datetime import datetime
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf

DAYS = [datetime(2026, 8, d) for d in (4, 6, 7, 11, 12, 13, 14)]
PER_DAY = int(os.environ.get("PER_DAY", "22"))
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "25"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
NUM = re.compile(r"\(?-?\d[\d,]*\.?\d*\)?")
SCALES = {"Rs million": 1.0, "Rs lakh": 10.0, "Rs crore": 0.1, "Rs thousand": 1000.0, "Rs actual": 1e6}

def nums(text):
    out = []
    for m in NUM.findall(text):
        neg = m.startswith("(") or m.startswith("-")
        s = m.strip("()-").replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        out.append(-v if neg else v)
    return out

def has(vals, target, tol_abs=0.011, tol_rel=2e-4):
    t = abs(target)
    return any(abs(abs(v) - t) <= max(tol_abs, tol_rel * t) for v in vals)

def pdf_text(content):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(content))
    pages = len(r.pages)
    txt = ""
    for pg in r.pages[:14]:
        try:
            txt += (pg.extract_text() or "") + "\n"
        except Exception:
            pass
    return pages, txt

def main():
    t_end = time.time() + BUDGET_MIN * 60
    stats, rows = {}, []
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
                stats["no_quarter_in_headline"] = stats.get("no_quarter_in_headline", 0) + 1
                continue
            truth = {}
            for basis in ("consolidated", "standalone"):
                m = rf.fetch(bse, code, name, basis, q)
                if m and m.get("revenue") is not None and m.get("pat") is not None:
                    truth[basis] = m
            if not truth:
                stats["no_bse_table"] = stats.get("no_bse_table", 0) + 1
                continue
            try:
                resp = requests.get("https://www.bseindia.com/xml-data/corpfiling/AttachLive/" + r["ATTACHMENTNAME"], headers=UA, timeout=60)
                pages, txt = pdf_text(resp.content)
            except Exception as e:
                stats["pdf_error"] = stats.get("pdf_error", 0) + 1
                rows.append(f"{name[:26]:26} PDF_ERROR {repr(e)[:60]}")
                continue
            if len(txt.strip()) < 300:
                stats["scanned_or_no_text"] = stats.get("scanned_or_no_text", 0) + 1
                rows.append(f"{name[:26]:26} pages={pages} chars={len(txt.strip())} -> SCANNED/NO TEXT")
                continue
            vals = nums(txt)
            hit = None
            for basis, m in truth.items():
                for sname, k in SCALES.items():
                    if has(vals, m["revenue"] * k) and has(vals, m["pat"] * k):
                        hit = (basis, sname); break
                if hit: break
            key = "match" if hit else "text_but_no_match"
            stats[key] = stats.get(key, 0) + 1
            rows.append(f"{name[:26]:26} pages={pages} chars={len(txt.strip())} -> {key} {hit or ''}")
    p("SUMMARY:", stats)
    done = sum(stats.get(k, 0) for k in ("match", "text_but_no_match", "scanned_or_no_text", "pdf_error"))
    if done:
        p(f"tested {done} PDFs: match {stats.get('match', 0)} ({100 * stats.get('match', 0) / done:.0f}%), scanned {stats.get('scanned_or_no_text', 0)}, text-but-no-match {stats.get('text_but_no_match', 0)}")
    for x in rows[:120]:
        p(x)

try:
    main()
except Exception as e:
    import traceback
    p("Caught error:", repr(e)[:300], traceback.format_exc()[-500:])
publish()
