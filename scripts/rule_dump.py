"""Debug: show how the rule reader sees the table rows of a few real filings (read-only)."""
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import rule_read as rr
import pdf_card as pc
import rule_validate as rv

N = int(os.environ.get("N", "6"))
SKIP = int(os.environ.get("SKIP", "0"))
ONLY = [x.strip().lower() for x in os.environ.get("ONLY", "").split(",") if x.strip()]
def main():
    with BSE(download_folder="./") as bse:
        fl = rv.filings(bse)
    k = 0
    for rec in fl:
        nm = rec["SLONGNAME"]
        if ONLY and not any(o in nm.lower() for o in ONLY): continue
        c = rv.get(rec)
        if not c: continue
        small = pc.trim_pdf(c)
        out, err = rr.read_pdf(small, hint=rec.get("NEWSSUB") or "")
        if out is not None and not ONLY: continue
        k += 1
        if k <= SKIP and not ONLY: continue
        p("=====", nm, "|", err, "| pages", len(__import__("fitz").open(stream=small, filetype="pdf")))
        pages = rr._pdf_rows(small)
        shown = 0
        for pno, (txt, rws) in enumerate(pages):
            low = txt.lower()
            if sum(x in low for x in rr.KEYS) < 2: continue
            p("-- page", pno + 1)
            for r in rws[:75]:
                lb, nums = rr.split_row(r)
                p("  ", lb[:60], "||", nums[:8])
            shown += 1
            if shown >= 1: break
        if k >= N + (0 if ONLY else SKIP): break
    publish()
if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; p("ERROR", traceback.format_exc()[-1500:]); publish()
