"""Read-only: download NSE result PDFs several ways; read MAHLIFE with and without page trimming."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import requests
import nse_results as nr, pdf_card as pc, gemini_read as gr
try:
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    rows = nr.fetch_day(datetime.now(IST).replace(tzinfo=None)) or []
    for sym in ("HAVELLS", "MAHLIFE"):
        xs = [r for r in rows if r.get("symbol") == sym and (r.get("desc") or "") == "Outcome of Board Meeting"]
        if not xs: p(sym, "no row"); continue
        x = xs[0]; url = x["attchmntFile"]
        p(sym, url, "text:", str(x.get("attchmntText"))[:120], "size:", x.get("attFileSize"))
        got = {}
        for label, kw in (("session+ref", dict(headers={"Referer": nr.REF})), ("session-noref", {}), ):
            try:
                r = nr.sess().get(url, timeout=60, **kw); got[label] = r.content
                p(" ", label, r.status_code, len(r.content), r.headers.get("content-type"), r.content[:8])
            except Exception as e: p(" ", label, "ERR", repr(e)[:100])
        for label, hd in (("plain-UA", nr.UA), ("plain-UA+ref", dict(nr.UA, Referer=nr.REF)), ("bare", {"User-Agent": "Mozilla/5.0"})):
            try:
                r = requests.get(url, headers=hd, timeout=60); got[label] = r.content
                p(" ", label, r.status_code, len(r.content), r.headers.get("content-type"), r.content[:8])
            except Exception as e: p(" ", label, "ERR", repr(e)[:100])
        if sym == "MAHLIFE":
            pdf = next((v for v in got.values() if v[:4] == b"%PDF"), b"")
            if pdf:
                import fitz
                p("pages", fitz.open(stream=pdf, filetype="pdf").page_count, "trimmed pages", fitz.open(stream=pc.trim_pdf(pdf), filetype="pdf").page_count)
                for lab, b in (("trimmed", pc.trim_pdf(pdf)), ("full", pdf)):
                    out, err = gr.read_pdf(pc.geminikey(), pc.MODEL, b, tries=2, timeout=120)
                    p(lab, "err", err)
                    if out:
                        for basis in ("consolidated", "standalone"):
                            d = out.get(basis)
                            if d: p(" ", lab, basis, "arith", [nr.arith_col(d, i) for i in range(3)], json.dumps({k: d.get(k) for k in ("revenue","total_income","total_expenses","pbt","tax","pat")}))
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-800:])
publish()
