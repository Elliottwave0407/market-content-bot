import sys, os, re, io
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
s = nse.sess()
u = "https://nsearchives.nseindia.com/corporate/E2E_16102026195347_SESignedRecordingweblink.pdf"
r = s.get(u, timeout=60)
p("pdf status", r.status_code, len(r.content))
try:
    from pypdf import PdfReader
    txt = " ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
    p("text chars", len(txt))
    p("urls:", re.findall(r"https?://\S+", txt))
    try:
        for pg in PdfReader(io.BytesIO(r.content)).pages:
            for a in pg.get("/Annots") or []:
                o = a.get_object()
                if "/A" in o and "/URI" in o["/A"]:
                    p("link annot:", o["/A"]["/URI"])
    except Exception as e:
        p("annot err", repr(e)[:80])
except Exception as e:
    p("pdf err", repr(e)[:120])
publish()
