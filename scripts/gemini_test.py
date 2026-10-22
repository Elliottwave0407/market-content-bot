"""Dry test of gemini_read.read_pdf (fallback on 429) with a synthetic results PDF. Read-only."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import fitz
import gemini_read as gr, pdf_card as pc
try:
    d = fitz.open(); pg = d.new_page()
    rows = ["Statement of Unaudited Financial Results", "Rs. in Lakhs", "Particulars | 30.09.2026 | 30.06.2026 | 30.09.2025",
            "Revenue from operations | 1,200.00 | 1,100.00 | 1,000.00", "Other income | 20.00 | 15.00 | 10.00",
            "Total income | 1,220.00 | 1,115.00 | 1,010.00", "Total expenses | 1,000.00 | 950.00 | 900.00",
            "Finance costs | 30.00 | 28.00 | 25.00", "Depreciation | 40.00 | 38.00 | 35.00",
            "Profit before tax | 220.00 | 165.00 | 110.00", "Tax | 55.00 | 40.00 | 28.00", "Net profit | 165.00 | 125.00 | 82.00", "EPS | 1.65 | 1.25 | 0.82"]
    y = 60
    for t in rows: pg.insert_text((40, y), t, fontsize=11); y += 22
    pdf = d.tobytes()
    key = pc.geminikey()
    for models in (None, "bogus-model-xyz"):
        t0 = time.time()
        m = models or pc.MODEL
        out, err = gr.read_pdf(key, m, pdf, tries=2, timeout=90)
        p("model", m, "err", err, "secs", round(time.time() - t0, 1))
        p(json.dumps(out)[:500] if out else "no output")
    p("quota", json.dumps({k: round(v - time.time()) for k, v in gr.QUOTA["until"].items()}))
except Exception as e:
    import traceback; p("ERROR", repr(e)); p(traceback.format_exc()[-1200:])
publish()
