"""Daily price store for the ESM engine: NSE and BSE bhavcopy (UDiFF) for every equity-like series, kept compactly in store/prices/YYYY-MM.csv.gz.
Columns: d,src,isin,sym,ser,o,h,l,c,pc,v   (pc = previous close as given by the exchange, adjusted on ex-dates, so chained returns are corporate-action adjusted).
Resumes: dates already stored are skipped; market holidays are remembered in store/prices/_nodata.json. Read-only on the exchanges; posts nothing.
Env: FROM_DATE (YYYY-MM-DD, default 2024-07-01), BUDGET_MIN (default 40)."""
import os, sys, io, csv, gzip, json, time, zipfile, glob, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
from datetime import datetime, timedelta
ROOT = "store/prices"; os.makedirs(ROOT, exist_ok=True)
FROM = os.environ.get("FROM_DATE", "2024-07-01"); BUDGET = float(os.environ.get("BUDGET_MIN", "40")) * 60; T0 = time.time()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
NSE_SER = {"EQ", "BE", "BZ", "SM", "ST", "SZ", "SO"}
BSE_SER = {"A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "F", "S", "G"}
COLS = ["d", "src", "isin", "sym", "ser", "o", "h", "l", "c", "pc", "v"]

os.makedirs(f"{ROOT}/d", exist_ok=True)
def save_day(key, s, rows):
    rows.sort(key=lambda r: r[3])
    with gzip.open(f"{ROOT}/d/{key}_{s}.csv.gz", "wt", encoding="utf-8", newline="") as fh: csv.writer(fh).writerows(rows)

def nse_day(d):
    r = requests.get(f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", headers=UA, timeout=60)
    if r.status_code != 200 or r.content[:2] != b"PK": return None
    z = zipfile.ZipFile(io.BytesIO(r.content)); out = []
    for x in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore"))):
        if x["SctySrs"] in NSE_SER and x["ClsPric"]:
            out.append([f"{d:%Y-%m-%d}", "N", x["ISIN"], x["TckrSymb"], x["SctySrs"], x["OpnPric"], x["HghPric"], x["LwPric"], x["ClsPric"], x["PrvsClsgPric"], x["TtlTradgVol"]])
    return out

def bse_day(b, d):
    f = b.bhavcopyReport(d, folder=tempfile.mkdtemp())
    out = []
    with open(f, encoding="utf-8", errors="ignore") as fh:
        for x in csv.DictReader(fh):
            if x.get("SctySrs") in BSE_SER and x.get("ClsPric") and x.get("FinInstrmTp") == "STK":
                out.append([f"{d:%Y-%m-%d}", "B", x["ISIN"], x["FinInstrmId"], x["SctySrs"], x["OpnPric"], x["HghPric"], x["LwPric"], x["ClsPric"], x["PrvsClsgPric"], x["TtlTradgVol"]])
    return out

try:
    from bse import BSE
    try: nodata = json.load(open(f"{ROOT}/_nodata.json"))
    except Exception: nodata = {"N": [], "B": []}
    have = {"N": set(), "B": set()}
    for f in glob.glob(f"{ROOT}/d/*.csv.gz"):
        b0 = os.path.basename(f); have[b0[11]].add(b0[:10])
    try: fails = json.load(open(f"{ROOT}/_fails.json"))
    except Exception: fails = {}
    start = datetime.strptime(FROM, "%Y-%m-%d"); end = datetime.utcnow() + timedelta(hours=5, minutes=30)
    days = []; d = start
    while d.date() <= end.date():
        if d.weekday() < 5: days.append(d)
        d += timedelta(days=1)
    # newest first so the daily run is instant and a backfill works backwards from today
    days.sort(reverse=True)
    todo = [(d, s) for d in days for s in ("N", "B") if f"{d:%Y-%m-%d}" not in have[s] and f"{d:%Y-%m-%d}" not in nodata[s]]
    p("trading-day slots to fetch:", len(todo), "| stored NSE days:", len(have["N"]), "BSE days:", len(have["B"]))
    buf = {}; done_n = {"N": 0, "B": 0}; ctx = BSE(download_folder=tempfile.mkdtemp()); b = ctx.__enter__()
    def flush():
        json.dump(fails, open(f"{ROOT}/_fails.json", "w"))
    for i, (d, s) in enumerate(todo):
        if time.time() - T0 > BUDGET: break
        key = f"{d:%Y-%m-%d}"; m = key[:7]
        try:
            rows = nse_day(d) if s == "N" else bse_day(b, d)
        except Exception as e:
            if s == "B" and "unavailable" in str(e).lower() or "not yet" in str(e).lower(): rows = None
            else:
                fk = s + key; fails[fk] = fails.get(fk, 0) + 1
                if fails[fk] >= 3: nodata[s].append(key)    # give up after 3 failed runs, so the chain cannot loop forever
                p("error", s, key, type(e).__name__, repr(e)[:70]); rows = "err"
        if rows == "err": continue
        if not rows:
            if (datetime.utcnow() + timedelta(hours=5, minutes=30)).date() - d.date() > timedelta(days=1): nodata[s].append(key)
        else:
            save_day(key, s, rows); done_n[s] += 1; have[s].add(key)
        if (i + 1) % 25 == 0:
            flush(); json.dump(nodata, open(f"{ROOT}/_nodata.json", "w"))
        time.sleep(0.25)
    flush(); json.dump(nodata, open(f"{ROOT}/_nodata.json", "w"))
    try: ctx.__exit__(None, None, None)
    except Exception: pass
    left = len([1 for d, s in todo if f"{d:%Y-%m-%d}" not in have[s] and f"{d:%Y-%m-%d}" not in nodata[s]])
    progress = done_n["N"] + done_n["B"] > 0
    p("fetched days: NSE", done_n["N"], "BSE", done_n["B"], "| still to fetch:", left, "| holidays/no-data remembered:", len(nodata["N"]), len(nodata["B"]))
    open(f"{ROOT}/_more.flag", "w").write("1" if (left and progress) else "0")
except Exception:
    p("ERROR", traceback.format_exc()[-700:])
publish()
