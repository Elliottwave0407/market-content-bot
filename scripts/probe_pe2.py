import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
try:
    import yfinance as yf
    for sym in ["REFRACTORY", "TSCINDIA", "ONYX", "ABMINTLLTD", "SHREEDHAR", "OPTIVALUE", "RELIANCE"]:
        try:
            i = yf.Ticker(sym + ".NS").info
            p(sym, {k: i.get(k) for k in ["trailingPE", "trailingEps", "marketCap", "currentPrice", "forwardPE"]})
        except Exception as e: p(sym, "ERR", repr(e)[:80])
except Exception as e: p("yf ERR", repr(e)[:150])
try:
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for code in ["500325"]:
            for fn in ["quote", "getScripHeaderData", "scripHeader"]:
                if hasattr(b, fn):
                    try: r = getattr(b, fn)(code); p(fn, str(r)[:500])
                    except Exception as e: p(fn, "ERR", repr(e)[:100])
        p("bse methods:", [m for m in dir(b) if not m.startswith("_")][:60])
except Exception as e: p("bse ERR", repr(e)[:150])
publish()
