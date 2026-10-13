"""Read-only probe: how many stocks per segment can we get from NSE + BSE daily files, and how do they overlap (by ISIN)?"""
import os, io, csv, sys, zipfile, glob, tempfile
from datetime import datetime, timedelta
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
s = requests.Session()

def nse_full(d):
    r = s.get(f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv", headers=UA, timeout=40)
    if r.status_code != 200:
        return None
    rows = [{k.strip(): (v or "").strip() for k, v in x.items() if k} for x in csv.DictReader(io.StringIO(r.text))]
    return rows if rows and datetime.strptime(rows[0]["DATE1"], "%d-%b-%Y").date() == d.date() else None

day = None
for back in range(0, 6):
    d = datetime.now() - timedelta(days=back)
    if d.weekday() >= 5:
        continue
    rows = nse_full(d)
    if rows:
        day = d
        break
p("NSE day:", day and f"{day:%Y-%m-%d}", "rows:", len(rows or []))
ser = Counter(r["SERIES"] for r in rows)
p("NSE rows by series:", dict(ser.most_common(12)))
def to_f(x):
    try: return float(x)
    except: return 0.0
for sname in ("EQ", "BE", "SM", "ST", "BZ"):
    t = [to_f(r["TURNOVER_LACS"]) for r in rows if r["SERIES"] == sname]
    if t:
        t.sort()
        p(f"NSE {sname}: n={len(t)} traded(turn>0)={sum(1 for x in t if x > 0)} >=100lac={sum(1 for x in t if x >= 100)} >=10lac={sum(1 for x in t if x >= 10)} median={t[len(t)//2]:.1f} lac")

# NSE symbol -> ISIN
isin_nse = {}
for u in ("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"):
    try:
        r = s.get(u, headers=UA, timeout=40)
        n = 0
        for x in csv.DictReader(io.StringIO(r.text)):
            x = {k.strip(): (v or "").strip() for k, v in x.items() if k}
            if x.get("SYMBOL") and x.get("ISIN NUMBER"):
                isin_nse[x["SYMBOL"]] = x["ISIN NUMBER"]; n += 1
        p("ISIN list", u.rsplit("/", 1)[-1], r.status_code, n)
    except Exception as e:
        p("ISIN list failed", u.rsplit("/", 1)[-1], repr(e)[:100])
nse_isins = {isin_nse.get(r["SYMBOL"]) for r in rows if r["SERIES"] in ("EQ", "BE", "SM", "ST", "BZ") and to_f(r["TURNOVER_LACS"]) > 0} - {None}
p("NSE traded stocks with ISIN:", len(nse_isins))

# BSE bhavcopy
from bse import BSE
tmp = tempfile.mkdtemp()
bse_rows = []
with BSE(download_folder=tmp) as b:
    for back in range(0, 6):
        d = (day or datetime.now()) - timedelta(days=back)
        try:
            path = b.bhavcopyReport(d, tmp)
            p("BSE bhavcopy ok for", f"{d:%Y-%m-%d}", str(path).rsplit("/", 1)[-1])
            break
        except Exception as e:
            p("BSE bhavcopy fail", f"{d:%Y-%m-%d}", repr(e)[:120])
            path = None
    if path:
        txt = open(path, encoding="utf-8", errors="ignore").read() if not str(path).endswith(".zip") else None
        if txt is None:
            z = zipfile.ZipFile(path); txt = z.read(z.namelist()[0]).decode("utf-8", "ignore")
        rd = list(csv.DictReader(io.StringIO(txt)))
        p("BSE columns:", list(rd[0].keys()))
        p("BSE sample row:", {k: v for k, v in list(rd[0].items())[:14]})
        bse_rows = rd
    p("BSE rows:", len(bse_rows))
    keys = list(bse_rows[0].keys()) if bse_rows else []
    gk = next((k for k in keys if k.strip().lower() in ("sc_group", "group", "scrip_group", "sctygrp")), None)
    ik = next((k for k in keys if "isin" in k.lower()), None)
    tk = next((k for k in keys if "net_turnov" in k.lower() or k.strip().lower() in ("net_turnover", "nettrdval")), None)
    p("BSE keys group/isin/turnover:", gk, ik, tk)
    if gk:
        p("BSE rows by group:", dict(Counter(r[gk].strip() for r in bse_rows).most_common(20)))
    if ik:
        bse_isins = {r[ik].strip() for r in bse_rows if r[ik].strip()}
        only_bse = bse_isins - nse_isins
        p("BSE ISINs:", len(bse_isins), "| also on NSE (traded):", len(bse_isins & nse_isins), "| BSE-only:", len(only_bse))
        if gk:
            p("BSE-only by group:", dict(Counter(r[gk].strip() for r in bse_rows if r[ik].strip() in only_bse).most_common(20)))
        p("combined unique traded ISINs:", len(bse_isins | nse_isins))
    # listSecurities for market cap coverage
    try:
        tot = 0; withcap = 0
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "IP", "R", "P", "Y", "ZP", "TS"):
            try:
                ls = b.listSecurities(group=g)
            except Exception:
                continue
            tot += len(ls); withcap += sum(1 for x in ls if x.get("Mktcap") not in (None, "", 0, "0"))
        p("BSE listSecurities total:", tot, "with Mktcap:", withcap)
    except Exception as e:
        p("listSecurities failed", repr(e)[:100])
publish()
