"""Read-only: can a runner get (1) NSE daily bhavcopy history (prices, prev close), (2) NSE daily market-cap file, (3) the daily ESM circular ZIP contents? Used to plan price history for stocks under Rs 1,000 Cr and the ESM entry/exit levels."""
import os, sys, io, csv, zipfile, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
def get(u):
    try:
        r = requests.get(u, headers=UA, timeout=60); return r
    except Exception as e:
        p("  error", u[-60:], type(e).__name__); return None
try:
    for d in ("20261027", "20260930", "20251027", "20250731"):
        r = get(f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip")
        if r is not None and r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content)); rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore"))))
            ser = {}
            for x in rows: ser[x.get("SctySrs")] = ser.get(x.get("SctySrs"), 0) + 1
            p("BHAV", d, "rows", len(rows), "series", ser, "cols", list(rows[0].keys())[:40])
            if d == "20261027": p("  sample", {k: rows[0][k] for k in ("TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric", "ISIN") if k in rows[0]})
        else: p("BHAV", d, r.status_code if r is not None else None)
    for u in ("https://nsearchives.nseindia.com/archives/equities/mcap/MCAP_27102026.zip", "https://nsearchives.nseindia.com/archives/equities/mcap/MCAP_24102026.zip",
              "https://nsearchives.nseindia.com/content/equities/MCAP_27102026.csv", "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_27102026.csv"):
        r = get(u); p("MCAP?", u[-48:], r.status_code if r is not None else None, len(r.content) if r is not None else 0, (r.content[:200] if r is not None and r.status_code == 200 else b""))
    r = get("https://nsearchives.nseindia.com/content/circulars/SURV77129.zip")
    if r is not None and r.status_code == 200:
        z = zipfile.ZipFile(io.BytesIO(r.content)); p("ESM ZIP files:", z.namelist())
        for n in z.namelist()[:2]:
            b = z.read(n); p("  ", n, len(b), b[:600])
            if n.lower().endswith((".xlsx", ".xls")):
                try:
                    import openpyxl; wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True)
                    for ws in wb.worksheets[:2]:
                        p("  sheet", ws.title, [list(r_) for r_ in list(ws.iter_rows(values_only=True))[:8]])
                except Exception as e: p("  xlsx read error", repr(e)[:80])
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
