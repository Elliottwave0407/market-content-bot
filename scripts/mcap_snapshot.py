"""Market-cap and F&O snapshot for the ESM engine: BSE listSecurities (ISIN, Mktcap) for all groups, plus NSE F&O stock list.
Writes store/mcap/mcap.json {isin: {m: mcap, s: bse code, g: group, n: symbol}} and store/mcap/fno.json. Posts nothing."""
import os, sys, json, tempfile, time, traceback, requests
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
os.makedirs("store/mcap", exist_ok=True)
try:
    from bse import BSE
    out = {}; sample = None
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "X", "XT", "T", "Z", "M", "MT", "MS", "P", "R", "F", "IF", "XD", "ZP", "SS", "ST", "Y"):
            try:
                rows = b.listSecurities(group=g)
                if rows and sample is None: sample = {k: rows[0][k] for k in list(rows[0])[:25]}
                for r in rows:
                    i = r.get("ISIN_NUMBER")
                    try: m = float(str(r.get("Mktcap")).replace(",", ""))
                    except Exception: m = None
                    if i: out[i] = {"m": m, "s": str(r.get("SCRIP_CD")).strip(), "g": g, "n": r.get("scrip_id")}
                p("BSE group", g, len(rows))
            except Exception as e: p("BSE group", g, "none", type(e).__name__)
    p("sample row:", sample)
    json.dump(out, open("store/mcap/mcap.json", "w"), separators=(",", ":"))
    p("isins:", len(out), "with mcap:", sum(1 for v in out.values() if v["m"]))
    ms = sorted(v["m"] for v in out.values() if v["m"])
    if ms: p("mcap quantiles (as given):", [ms[int(len(ms) * q)] for q in (0.1, 0.5, 0.9)], "max", ms[-1])
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    for u in ["https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv", "https://nsearchives.nseindia.com/content/fo/fo_mktlots_1.csv"]:
        r = requests.get(u, headers=UA, timeout=40); p("fno", u[-18:], r.status_code, len(r.content))
        if r.status_code == 200 and len(r.content) > 500:
            rows = [l.split(",") for l in r.text.splitlines()[1:]]
            syms = sorted({x[1].strip() for x in rows if len(x) > 2 and x[1].strip() and "NIFTY" not in x[1].upper() and x[1].strip() not in ("SYMBOL",)})
            json.dump(syms, open("store/mcap/fno.json", "w")); p("fno symbols:", len(syms), syms[:6]); break
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
