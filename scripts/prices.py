"""NSE daily price history (free sec_bhavdata_full files). Cached on disk (Actions cache) - never committed to the repo.
ensure(days_back) downloads only missing days; load() returns one DataFrame; breadth() computes market-breadth numbers."""
import os, io, csv, gzip, time, glob
from datetime import datetime, timedelta
import requests

DIR = os.environ.get("PRICE_DIR", "data/prices")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
KEEP = ("EQ", "BE")
COLS = ["SYMBOL", "SERIES", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS", "DELIV_PER"]

def _path(d, ext):
    return os.path.join(DIR, f"{d:%Y-%m-%d}.{ext}")

def fetch_day(d, session):
    """rows for trading day d, 'holiday' if NSE served another day's data / no file, None on transient error."""
    u = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
    try:
        r = session.get(u, headers=UA, timeout=40)
    except Exception:
        return None
    if r.status_code == 404:
        return "nofile"
    if r.status_code != 200:
        return None
    rows = []
    file_date = None
    for x in csv.DictReader(io.StringIO(r.text)):
        x = {k.strip(): (v or "").strip() for k, v in x.items() if k}
        file_date = file_date or x.get("DATE1")
        if x.get("SERIES") in KEEP:
            rows.append([x.get(c, "") for c in COLS])
    if not file_date:
        return None
    if datetime.strptime(file_date, "%d-%b-%Y").date() != d.date():
        return "holiday"
    return rows

def ensure(days_back=430, max_new=500, log=print):
    os.makedirs(DIR, exist_ok=True)
    s = requests.Session()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new = 0
    for back in range(days_back, -1, -1):
        d = today - timedelta(days=back)
        if d.weekday() >= 5 or os.path.exists(_path(d, "csv.gz")) or os.path.exists(_path(d, "skip")):
            continue
        if new >= max_new:
            break
        res = fetch_day(d, s)
        time.sleep(0.25)
        if res is None:
            log(f"transient error {d.date()}")
            continue
        recent = back <= 2
        if isinstance(res, str):
            if not recent:                      # old holiday: remember so we never ask again
                open(_path(d, "skip"), "w").write(res)
            continue
        with gzip.open(_path(d, "csv.gz"), "wt", newline="") as fh:
            csv.writer(fh).writerows([COLS] + res)
        new += 1
    log(f"downloaded {new} new day files")
    return new

def load():
    import pandas as pd
    frames = []
    for f in sorted(glob.glob(os.path.join(DIR, "*.csv.gz"))):
        df = pd.read_csv(f)
        df["date"] = os.path.basename(f)[:10]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"symbol": "sym", "prev_close": "prev", "open_price": "open", "high_price": "high", "low_price": "low", "close_price": "close", "ttl_trd_qnty": "vol", "turnover_lacs": "turn", "deliv_per": "deliv"})
    for c in ("prev", "open", "high", "low", "close", "vol", "turn", "deliv"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["sym", "date"]).reset_index(drop=True)

def adjusted(df):
    """Back-adjust for splits/bonuses: NSE's PREV_CLOSE is already adjusted on the ex-date, so prev/close(yesterday) gives the factor."""
    import numpy as np
    df = df.copy()
    prev_close = df.groupby("sym")["close"].shift(1)
    r = (df["prev"] / prev_close).where(prev_close.notna())
    r = r.where((r - 1).abs() > 0.004, 1.0).fillna(1.0)
    r = r.where((r > 0.01) & (r < 100), 1.0)
    # factor applied to all rows BEFORE the event = product of r from later rows
    df["_r"] = r
    fac = df.groupby("sym")["_r"].transform(lambda s: s[::-1].cumprod()[::-1].shift(-1).fillna(1.0))
    for c in ("open", "high", "low", "close", "prev"):
        df[c] = df[c] * fac
    return df.drop(columns=["_r"])

def breadth(df, turnover_min_lacs=100):
    """Market breadth for the latest date. Universe = EQ/BE with >= 1 Cr turnover that day (liquid), plus all-EQ counts."""
    import numpy as np
    df = adjusted(df)
    last = df["date"].max()
    g = df.groupby("sym")
    df["ma20"] = g["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["ma50"] = g["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    df["ma200"] = g["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
    df["hi52"] = g["high"].transform(lambda s: s.shift(1).rolling(250, min_periods=120).max())
    df["lo52"] = g["low"].transform(lambda s: s.shift(1).rolling(250, min_periods=120).min())
    t = df[df["date"] == last].copy()
    allq = t[t["series"] == "EQ"]
    liq = t[(t["turn"] >= turnover_min_lacs)]
    def stats(x):
        adv = int((x["close"] > x["prev"] * 1.0001).sum()); dec = int((x["close"] < x["prev"] * 0.9999).sum())
        out = {"n": int(len(x)), "adv": adv, "dec": dec, "unch": int(len(x)) - adv - dec}
        for k in ("ma20", "ma50", "ma200"):
            v = x[x[k].notna()]
            out["above_" + k[2:]] = round(100 * float((v["close"] > v[k]).mean()), 1) if len(v) else None
            out["n_" + k[2:]] = int(len(v))
        out["new_high"] = int((x["high"] > x["hi52"]).sum()); out["new_low"] = int((x["low"] < x["lo52"]).sum())
        out["up4"] = int((x["close"] / x["prev"] - 1 >= 0.04).sum()); out["down4"] = int((x["close"] / x["prev"] - 1 <= -0.04).sum())
        return out
    return {"date": last, "all_eq": stats(allq), "liquid": stats(liq)}
