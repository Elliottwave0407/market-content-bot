import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
try:
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for code in ["500325", "543982"]:
            for fn in ["equityMetaInfo", "resultsSnapshot", "getScripTradingStats"]:
                try: r = getattr(b, fn)(code); p(code, fn, str(r)[:700])
                except Exception as e: p(code, fn, "ERR", repr(e)[:100])
except Exception as e: p("bse ERR", repr(e)[:150])
try:
    import yfinance as yf
    for sym in ["TSCINDIA", "ONYX", "RELIANCE"]:
        try:
            i = yf.Ticker(sym + ".NS").info
            p(sym, {k: i.get(k) for k in ["trailingPE", "trailingEps", "marketCap"]})
        except Exception as e: p(sym, "ERR", repr(e)[:80])
except Exception as e: p("yf ERR", repr(e)[:100])
publish()
