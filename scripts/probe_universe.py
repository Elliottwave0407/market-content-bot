"""Read-only probe 2: NSE UDiFF bhavcopy (has ISIN + all series) + BSE bhavcopy -> per-segment counts, liquidity, overlap by ISIN."""
import os, io, csv, sys, zipfile, tempfile
from datetime import datetime, timedelta
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
s = requests.Session()
def f(x):
    try: return float(x)
    except Exception: return 0.0

nse, day = None, None
for back in range(0, 6):
    d = datetime.now() - timedelta(days=back)
    if d.weekday() >= 5:
        continue
    u = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    r = s.get(u, headers=UA, timeout=60)
    p("NSE UDiFF", f"{d:%Y-%m-%d}", r.status_code, len(r.content))
    if r.status_code == 200:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nse = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore"))))
        day = d
        break
if nse:
    p("NSE columns:", list(nse[0].keys()))
    sk = "SctySrs"
    p("NSE by series:", dict(Counter(r[sk].strip() for r in nse).most_common(15)))
    for sn in ("EQ", "BE", "SM", "ST", "BZ"):
        t = sorted(f(r["TtlTrfVal"]) / 1e5 for r in nse if r[sk].strip() == sn)   # Rs lakh
        if t:
            p(f"NSE {sn}: n={len(t)} >=1Cr={sum(1 for x in t if x >= 100)} >=25lac={sum(1 for x in t if x >= 25)} >=5lac={sum(1 for x in t if x >= 5)} median={t[len(t)//2]:.1f}lac")
    nse_isin = {r["ISIN"].strip() for r in nse if f(r["TtlTrfVal"]) > 0 and r["ISIN"].strip()}
    p("NSE traded ISINs:", len(nse_isin))

from bse import BSE
tmp = tempfile.mkdtemp()
with BSE(download_folder=tmp) as b:
    path = b.bhavcopyReport(day or datetime.now(), tmp)
    txt = open(path, encoding="utf-8", errors="ignore").read()
    bs = list(csv.DictReader(io.StringIO(txt)))
    p("BSE rows:", len(bs), "by series/group:", dict(Counter(r["SctySrs"].strip() for r in bs).most_common(25)))
    for g in sorted({r["SctySrs"].strip() for r in bs}):
        t = sorted(f(r["TtlTrfVal"]) / 1e5 for r in bs if r["SctySrs"].strip() == g)
        if len(t) >= 20:
            p(f"BSE {g}: n={len(t)} >=1Cr={sum(1 for x in t if x >= 100)} >=25lac={sum(1 for x in t if x >= 25)} >=5lac={sum(1 for x in t if x >= 5)} zero={sum(1 for x in t if x == 0)} median={t[len(t)//2]:.1f}lac")
    bse_tr = [r for r in bs if f(r["TtlTrfVal"]) > 0]
    bse_isin = {r["ISIN"].strip() for r in bse_tr}
    p("BSE traded ISINs:", len(bse_isin))
    if nse:
        both = bse_isin & nse_isin
        only = bse_isin - nse_isin
        p("both exchanges:", len(both), "| BSE-only:", len(only), "| NSE-only:", len(nse_isin - bse_isin), "| union:", len(bse_isin | nse_isin))
        og = Counter(r["SctySrs"].strip() for r in bse_tr if r["ISIN"].strip() in only)
        p("BSE-only by group:", dict(og.most_common(20)))
        big = sum(1 for r in bse_tr if r["ISIN"].strip() in only and f(r["TtlTrfVal"]) >= 1e7)
        mid = sum(1 for r in bse_tr if r["ISIN"].strip() in only and f(r["TtlTrfVal"]) >= 2.5e6)
        p("BSE-only with traded value >=1Cr:", big, ">=25 lac:", mid)
publish()
