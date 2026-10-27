"""Read-only probe 2: free sector/industry sources reachable from a GitHub runner? NSE index constituent CSVs (have an Industry column + ISIN), BSE security list ISIN field, Yahoo via yfinance."""
import os, sys, io, csv, json, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
tot = {}
for n in ("ind_nifty500list", "ind_niftymicrocap250_list", "ind_niftysmallcap250list", "ind_niftymidcap150list", "ind_niftylargemidcap250list", "ind_niftytotalmarket_list", "ind_niftysmallcap50list"):
    for host in ("nsearchives.nseindia.com", "archives.nseindia.com"):
        try:
            r = requests.get(f"https://{host}/content/indices/{n}.csv", headers=UA, timeout=30)
            if r.status_code == 200 and "ISIN" in r.text[:300]:
                rows = list(csv.DictReader(io.StringIO(r.text)))
                for x in rows: tot[x.get("ISIN Code")] = x.get("Industry")
                p("NSE", n, host, "rows", len(rows), "cols", list(rows[0].keys()), "sample", list(rows[0].values())[:5]); break
            p("NSE", n, host, r.status_code)
        except Exception as e:
            p("NSE", n, host, "error", repr(e)[:70])
p("NSE union unique ISINs with industry:", len(tot), "| industries:", len(set(tot.values())), sorted(set(tot.values()))[:30])
try:
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        rows = b.listSecurities(group="A")
        p("BSE A rows", len(rows), "keys", sorted(rows[0].keys()), "sample", json.dumps(rows[0], default=str)[:300])
except Exception:
    p("bse err", traceback.format_exc()[-300:])
try:
    import subprocess; subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yfinance"], check=True)
    import yfinance as yf
    for t in ("POLYCAB.NS", "E2E.NS", "500002.BO", "TATAELXSI.NS"):
        try:
            i = yf.Ticker(t).info; p("YF", t, i.get("sector"), "|", i.get("industry"))
        except Exception as e:
            p("YF", t, "error", repr(e)[:90])
except Exception:
    p("yf err", traceback.format_exc()[-300:])
publish()
