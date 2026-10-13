import requests, io, csv, time
from datetime import datetime, timedelta
from ci_out import p, publish
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
def get(d):
    u = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
    r = requests.get(u, headers=UA, timeout=30)
    return r.status_code, r.text, len(r.content)
today = datetime(2026, 10, 13)
shown = False
ok = 0
for back in range(0, 16):
    d = today - timedelta(days=back)
    if d.weekday() >= 5:
        continue
    try:
        sc, txt, n = get(d)
    except Exception as e:
        p(d.date(), "ERR", repr(e)[:80]); continue
    if sc != 200 or "SYMBOL" not in txt[:200].upper():
        p(d.date(), sc, n, "no file"); continue
    rows = list(csv.DictReader(io.StringIO(txt)))
    keys = [k.strip() for k in rows[0].keys()]
    series = {}
    for r in rows:
        s = (r.get(" SERIES") or r.get("SERIES") or "").strip()
        series[s] = series.get(s, 0) + 1
    p(d.date(), sc, f"{n/1e6:.2f}MB", "rows", len(rows), "EQ:", series.get("EQ"), "BE:", series.get("BE"), "SM:", series.get("SM"), "ST:", series.get("ST"))
    if not shown:
        p("COLUMNS:", keys); p("SAMPLE:", [ {k.strip(): v.strip() for k, v in r.items()} for r in rows[:2]]); shown = True
    ok += 1
    time.sleep(0.5)
p("files found in last 16 days:", ok)
for lbl, d in (("1y ago", datetime(2025, 10, 13)), ("2y ago", datetime(2024, 10, 14)), ("5y ago", datetime(2021, 10, 13)), ("10y ago", datetime(2016, 10, 13))):
    for k in range(0, 4):
        dd = d + timedelta(days=k)
        if dd.weekday() >= 5: continue
        try:
            sc, txt, n = get(dd); p(lbl, dd.date(), sc, n); 
            if sc == 200: break
        except Exception as e:
            p(lbl, dd.date(), "ERR", repr(e)[:60])
publish()
