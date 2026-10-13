"""Full-universe daily prices: NSE (EQ/BE/SM/ST/BZ) + BSE equity groups, from the exchanges' own daily files (UDiFF format, has ISIN).
Cached on disk (Actions cache) - never committed. One stock = one ISIN; its history comes from ONE exchange (the busier one).
ensure(): download missing days. load(): DataFrame. breadth_segments(): breadth for All + Large&Mid / Small / Micro / SME."""
import os, io, csv, gzip, glob, time, zipfile, tempfile
from datetime import datetime, timedelta
import requests

DIR = os.environ.get("PRICE2_DIR", "data/prices2")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
NSE_SER = {"EQ", "BE", "SM", "ST", "BZ"}
NSE_SME = {"SM", "ST"}
BSE_GRP = {"A", "B", "T", "X", "XT", "Z", "M", "MT", "MS"}
BSE_SME = {"M", "MT", "MS"}
COLS = ["exch", "isin", "sym", "series", "prev", "open", "high", "low", "close", "vol", "val"]
# draft segment rules (printed on the card): market cap in Rs Cr (main board, current BSE market cap), liquidity floor = traded value that day in Rs lakh
SEGMENTS = [("Large & Mid", 10000, None, 100.0), ("Small", 2000, 10000, 10.0), ("Micro", 0, 2000, 10.0)]
SME_FLOOR = 5.0

def _f(x):
    try: return float(x)
    except Exception: return 0.0

def _equity_isin(i):
    return len(i) == 12 and i.startswith("INE") and i[7:9] == "01"

def _rows(rd, exch):
    out = []
    for r in rd:
        i = (r.get("ISIN") or "").strip()
        g = (r.get("SctySrs") or "").strip()
        if not _equity_isin(i):
            continue
        if exch == "NSE" and g not in NSE_SER:
            continue
        if exch == "BSE" and g not in BSE_GRP:
            continue
        out.append([exch, i, (r.get("TckrSymb") or "").strip(), g, r["PrvsClsgPric"], r["OpnPric"], r["HghPric"], r["LwPric"], r["ClsPric"], r["TtlTradgVol"], r["TtlTrfVal"]])
    return out

def _p(d, ext):
    return os.path.join(DIR, f"{d:%Y-%m-%d}.{ext}")

def fetch_nse(d, s):
    try:
        r = s.get(f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", headers=UA, timeout=60)
    except Exception:
        return None
    if r.status_code == 404:
        return "nofile"
    if r.status_code != 200:
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    rd = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore"))))
    if not rd or rd[0].get("TradDt", "")[:10] != f"{d:%Y-%m-%d}":
        return "nofile"
    return _rows(rd, "NSE")

def fetch_bse(d, bse, tmp):
    try:
        path = bse.bhavcopyReport(d, tmp)
        txt = open(path, encoding="utf-8", errors="ignore").read()
        os.remove(path)
    except Exception:
        return None
    rd = list(csv.DictReader(io.StringIO(txt)))
    if not rd or rd[0].get("TradDt", "")[:10] != f"{d:%Y-%m-%d}":
        return None
    return _rows(rd, "BSE")

def _save(path, rows):
    with gzip.open(path, "wt", newline="") as fh:
        csv.writer(fh).writerows([COLS] + rows)

def ensure(days_back=430, max_new=700, log=print):
    from bse import BSE
    os.makedirs(DIR, exist_ok=True)
    s = requests.Session()
    tmp = tempfile.mkdtemp()
    today = datetime.now()
    days = [today - timedelta(days=k) for k in range(0, days_back + 1) if (today - timedelta(days=k)).weekday() < 5]
    new = 0
    t0 = time.time()
    with BSE(download_folder=tmp) as bse:
        for d in days:
            if new >= max_new or time.time() - t0 > 30 * 60:
                break
            if os.path.exists(_p(d, "skip")):
                continue
            for tag in ("nse", "bse"):   # header-only files = written by a buggy earlier filter; refetch
                fp = _p(d, tag + ".csv.gz")
                if os.path.exists(fp) and os.path.getsize(fp) < 200:
                    os.remove(fp)
            if not os.path.exists(_p(d, "nse.csv.gz")):
                res = fetch_nse(d, s)
                if res == "nofile":
                    if d.date() < today.date():
                        open(_p(d, "skip"), "w").close()
                    continue
                if res is None:
                    continue
                _save(_p(d, "nse.csv.gz"), res); new += 1
                time.sleep(0.3)
            if not os.path.exists(_p(d, "bse.csv.gz")) and not os.path.exists(_p(d, "bse.none")):
                res = fetch_bse(d, bse, tmp)
                if res is None:
                    tries = int(open(_p(d, "bse.try")).read() or 0) + 1 if os.path.exists(_p(d, "bse.try")) else 1
                    open(_p(d, "bse.try"), "w").write(str(tries))
                    if tries >= 3 and d.date() < today.date():
                        open(_p(d, "bse.none"), "w").close()
                    continue
                _save(_p(d, "bse.csv.gz"), res); new += 1
    log(f"downloaded {new} new day files in {time.time() - t0:.0f}s")
    return new

def load():
    """One row per (ISIN, day), from the stock's primary exchange (higher total traded value over the window)."""
    import pandas as pd
    frames = []
    for f in sorted(glob.glob(os.path.join(DIR, "*.csv.gz"))):
        df = pd.read_csv(f)
        df["date"] = os.path.basename(f)[:10]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for c in ("prev", "open", "high", "low", "close", "vol", "val"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    tot = df.groupby(["isin", "exch"])["val"].sum().reset_index().sort_values("val", ascending=False)
    prim = tot.drop_duplicates("isin")[["isin", "exch"]].rename(columns={"exch": "pex"})
    df = df.merge(prim, on="isin")
    df = df[df["exch"] == df["pex"]].drop(columns=["pex"])
    df["turn"] = df["val"] / 1e5        # Rs lakh
    df["sym"] = df["isin"]               # adjusted() chains per 'sym'
    return df.sort_values(["sym", "date"]).reset_index(drop=True)

def mcaps():
    """ISIN -> market cap (Rs Cr) from BSE's security list (all groups)."""
    from bse import BSE
    out = {}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y"):
            try:
                for x in b.listSecurities(group=g):
                    v = _f(x.get("Mktcap"))
                    if x.get("ISIN_NUMBER") and v > 0:
                        out[x["ISIN_NUMBER"].strip()] = v
            except Exception:
                continue
    return out

def _stats(x):
    adv = int((x["close"] > x["prev"] * 1.0001).sum()); dec = int((x["close"] < x["prev"] * 0.9999).sum())
    out = {"n": int(len(x)), "adv": adv, "dec": dec, "unch": int(len(x)) - adv - dec}
    for k in ("ma20", "ma50", "ma200"):
        v = x[x[k].notna()]
        out["above_" + k[2:]] = round(100 * float((v["close"] > v[k]).mean()), 1) if len(v) else None
        out["n_" + k[2:]] = int(len(v))
    out["new_high"] = int((x["high"] > x["hi52"]).sum()); out["new_low"] = int((x["low"] < x["lo52"]).sum())
    chg = x["close"] / x["prev"] - 1
    out["up4"] = int((chg >= 0.04).sum()); out["down4"] = int((chg <= -0.04).sum())
    return out

def breadth_segments(df, mc):
    import prices
    df = prices.adjusted(df)
    last = df["date"].max()
    g = df.groupby("sym")
    df["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["ma50"] = g["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    df["ma200"] = g["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
    df["hi52"] = g["high"].transform(lambda s: s.shift(1).rolling(250, min_periods=120).max())
    df["lo52"] = g["low"].transform(lambda s: s.shift(1).rolling(250, min_periods=120).min())
    t = df[(df["date"] == last) & (df["val"] > 0)].copy()
    t["mc"] = t["isin"].map(mc)
    sme = ((t["exch"] == "NSE") & t["series"].isin(NSE_SME)) | ((t["exch"] == "BSE") & t["series"].isin(BSE_SME))
    parts, seg_stats = [], {}
    for name, lo, hi, floor in SEGMENTS:
        m = (~sme) & t["mc"].notna() & (t["mc"] >= lo) & ((t["mc"] < hi) if hi else True) & (t["turn"] >= floor)
        parts.append(t[m]); seg_stats[name] = _stats(t[m])
    m = sme & (t["turn"] >= SME_FLOOR)
    parts.append(t[m]); seg_stats["SME"] = _stats(t[m])
    import pandas as pd
    allp = pd.concat(parts)
    unclassified = int(((~sme) & t["mc"].isna()).sum())
    return {"date": last, "all": _stats(allp), "seg": seg_stats, "unclassified": unclassified,
            "traded_total": int(len(t)), "floors": {n: f for n, _, _, f in SEGMENTS} | {"SME": SME_FLOOR}}
