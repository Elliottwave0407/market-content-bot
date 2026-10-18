import os, sys, traceback, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
SYM = os.environ.get("SYMBOL", "E2E"); CODE = os.environ.get("SCRIP", "544783")
try:
    from bse import BSE
    s = nse.sess()
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        rows = fd.merged(s, SYM, b, CODE, SYM)
    p("== QUARTERS (Rs Cr) NSE+BSE merged"); fd.show(rows, p)
except Exception:
    p("ERR", traceback.format_exc()[-800:])
publish()
