import os, sys, runpy, traceback, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        runpy.run_path("scripts/esm_radar.py", run_name="__main__")
except BaseException:
    p("ERROR", traceback.format_exc()[-900:])
for ln in buf.getvalue().splitlines()[-12:]: p(ln[:400])
publish()
