"""Read-only diagnosis of result filings that only got a 'numbers not shown' stub card (posted key 'code|quarter|na', no full card).
For each stub filing: download the PDF from BSE, classify it (text layer / scanned) and try the readers in order:
  1) rule reader on the text layer, 2) rule reader with OCR (tesseract), 3) NVIDIA text reader (only if there is a text layer).
Every reader result has already passed its own strict arithmetic gate. Prints one line per filing and a summary. Posts nothing, writes no state.
Env: DAYS (BSE look-back, default 12), N (max filings, default 60), ONLY (comma list of BSE codes), NIM (1 = also try the NVIDIA reader, default 1)."""
import os, sys, json, re, time, traceback
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RULE_OCR"] = "1"
import requests
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
import results_fetcher as rf
import rule_read as rr
import pdf_card as pc

DAYS = int(os.environ.get("DAYS") or "12")
N = int(os.environ.get("N") or "60")
ONLY = [x.strip() for x in (os.environ.get("ONLY") or "").split(",") if x.strip()]
USE_NIM = os.environ.get("NIM", "1") == "1"
UA = rpl.UA if hasattr(rpl, "UA") else {"User-Agent": "Mozilla/5.0"}


def stub_codes():
    st = json.load(open("state/seen.json"))
    posted = set(st["posted"])
    out = {}
    for k in posted:
        if k.endswith("|na"):
            code, label = k.split("|")[:2]
            if any(f"{code}|{label}|{b}" in posted for b in ("consolidated", "standalone")):
                continue
            out[code] = label
    try:
        done = json.load(open("state/stub_fill.json")).get("done", {})
    except Exception:
        done = {}
    return {c: l for c, l in out.items() if f"{c}|{l}" not in done}


def download(att):
    for folder in ("AttachLive", "AttachHis"):
        try:
            r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{att}", headers=UA, timeout=45)
        except Exception:
            continue
        if r.content[:4] == b"%PDF":
            return r.content
    return b""


def text_layer(content):
    import fitz
    d = fitz.open(stream=content, filetype="pdf")
    n = sum(len(re.sub(r"\W", "", d[i].get_text())) for i in range(min(d.page_count, 12)))
    return d.page_count, n


def summ(out):
    try:
        qs = out.get("quarters") or out.get("cols") or []
        return str(out)[:160]
    except Exception:
        return "?"


def main():
    stubs = stub_codes()
    if ONLY:
        stubs = {c: stubs.get(c, '') for c in ONLY}      # explicit list: look at exactly these scrip codes, stub or not
    p("stub filings without a full card:", len(stubs))
    cnt = Counter()
    with BSE(download_folder="/tmp") as b:
        rpl.DAYS_BACK = DAYS
        rows = rpl.fetch_filings(b)
        seen = {}
        for r in rows:
            c = str(r.get("SCRIP_CD")).strip()
            if c in stubs and r.get("ATTACHMENTNAME") and not r.get("_EARLY") and (c not in seen or r["NEWS_DT"] > seen[c]["NEWS_DT"]):
                seen[c] = r
        p("stub filings found in the last", DAYS, "days:", len(seen))
        todo = sorted(seen.items(), key=lambda kv: pc.mcap_of(kv[0]))      # smallest first
        if ONLY:
            todo = [kv for kv in todo if kv[0] in ONLY]
        for c, r in todo[:N]:
            name = r["SLONGNAME"]
            headline = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat(r["NEWS_DT"][:19])
            q_head = rf.expected_quarter(headline, filed)
            content = download(r["ATTACHMENTNAME"])
            if not content:
                cnt["pdf_not_downloadable"] += 1; p(f"{c} {name[:26]}: PDF not downloadable"); continue
            try:
                pages, chars = text_layer(content)
            except Exception as e:
                cnt["pdf_unopenable"] += 1; p(f"{c} {name[:26]}: PDF unopenable {repr(e)[:50]}"); continue
            kind = "text" if chars >= 400 else "scanned"
            small = pc.trim_pdf(content)
            res, via, why = None, None, []
            for label, fn in (("rule", lambda: rr.read_pdf(small, hint=headline, qhint=q_head)),):
                try:
                    o, e = fn()
                except Exception as ex:
                    o, e = None, repr(ex)[:80]
                if o is not None:
                    res, via = o, label + ("+ocr" if o.get("_ocr") else "")
                else:
                    why.append(f"{label}: {str(e)[:90]}")
            if res is None and small is not content:
                try:
                    o, e = rr.read_pdf(content, hint=headline, qhint=q_head)
                    if o is not None:
                        res, via = o, "rule-full" + ("+ocr" if o.get("_ocr") else "")
                    else:
                        why.append(f"rule-full: {str(e)[:90]}")
                except Exception as ex:
                    why.append("rule-full err " + repr(ex)[:60])
            if res is None and USE_NIM and kind == "text":
                import nim_read as nr
                o, e = nr.read_pdf(small)
                if o is not None:
                    res, via = o, "nim"
                else:
                    why.append(f"nim: {str(e)[:90]}")
            empty = bool(res) and not (res.get("quarter_end_columns") or res.get("consolidated") or res.get("standalone"))
            if empty:
                via = None; why.append("reader returned no results table (filing probably has no numbers)")
            cnt[(kind, via or "none")] += 1
            if via is None:
                try:
                    import fitz
                    d_ = fitz.open(stream=content, filetype="pdf")
                    best, bn = "", -1
                    for i in range(d_.page_count):
                        t_ = d_[i].get_text(); n_ = len(re.findall(r"(?i)total income|revenue from operations|profit before tax|net profit", t_))
                        if n_ > bn: best, bn = t_, n_
                    p(f"   headline: {headline.strip()[:150]!r} | best page hits={bn} | text: {re.sub(r'\\s+', ' ', best)[:420]!r}")
                except Exception as ex:
                    p("   page peek failed", repr(ex)[:60])
            p(f"{c} {name[:28]} | {pages}p {kind} | {'READ via ' + via if via else 'NOT READ'} | " + ("; ".join(why)[:260] if not via else summ(res)[:120]))
    p("SUMMARY", dict(cnt))


try:
    main()
except Exception:
    p("ERROR", traceback.format_exc()[-900:])
publish()
