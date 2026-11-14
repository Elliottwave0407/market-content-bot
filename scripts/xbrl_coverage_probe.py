"""Read-only: how many result filers have structured XBRL on NSE (integrated-filing-results) for the Sep-26 period, and how soon after the announcement?
Env: DAYS (comma YYYY-MM-DD), MAXN (max symbols, default 120). Posts nothing."""
import os, sys, time, statistics
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["NSE_SME"] = "1"
import nse_results as nr
import fin_data as fd

days = [d for d in os.environ.get("DAYS", "2026-11-13,2026-11-14").split(",") if d]
maxn = int(os.environ.get("MAXN", "120"))
rows = []
for ds in days:
    day = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=nr.IST)
    for x in nr.result_rows(nr.fetch_day(day)):
        rows.append(x)
by = {}
for x in rows:
    by.setdefault(x["symbol"], x)
syms = list(by)[:maxn]
print("result filings:", len(rows), "| distinct symbols:", len(by), "| probing:", len(syms), flush=True)
s = nr.sess()
stat = {"equities": [0, 0], "sme": [0, 0]}
lags = []
nox = []
for sym in syms:
    x = by[sym]
    got, idxused = None, None
    for idx in ("equities", "sme"):
        try:
            r = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=30)
            d = r.json().get("data", []) if r.status_code == 200 and r.text.strip() else []
        except Exception:
            d = []
        if d:
            got, idxused = d, idx
            break
        time.sleep(0.2)
    ok = None
    if got:
        for y in got:
            if "Financial" in (y.get("type") or "") and y.get("xbrl") not in (None, "None") and str(y.get("qe_Date") or "").lower().startswith("30-sep-2026"):
                ok = y
                break
    k = idxused or "equities"
    stat[k][1] += 1
    if ok:
        stat[k][0] += 1
        try:
            a = datetime.strptime(x["an_dt"], "%d-%b-%Y %H:%M:%S")
            c = datetime.strptime((ok.get("creation_Date") or "")[:20].strip(), "%d-%b-%Y %H:%M:%S")
            lags.append((c - a).total_seconds() / 60)
        except Exception:
            pass
    else:
        nox.append(f"{sym}({k})")
    time.sleep(0.25)
print("XBRL for Sep-26 found:", {k: f"{v[0]}/{v[1]}" for k, v in stat.items()}, flush=True)
if lags:
    lags.sort()
    print("lag announcement->xbrl record (min): n=%d min=%.0f p50=%.0f p90=%.0f max=%.0f" % (len(lags), lags[0], statistics.median(lags), lags[int(0.9 * (len(lags) - 1))], lags[-1]), flush=True)
print("no XBRL:", ", ".join(nox[:60]), flush=True)
