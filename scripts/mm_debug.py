"""Read-only: for a list of NSE symbols, read their Sep-26 result filing with the rule reader and print what was read next to NSE's XBRL numbers."""
import os, sys, json, re
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RULE_OCR"] = "1"; os.environ["NSE_SME"] = "1"
import nse_results as nr, fin_data as fd, rule_read as rr, pdf_card as pc
SYMS = [s.strip().upper() for s in os.environ.get("SYMS", "").split(",") if s.strip()]
d0, d1 = datetime.strptime(os.environ.get("START", "2026-11-01"), "%Y-%m-%d"), datetime.strptime(os.environ.get("END", "2026-11-14"), "%Y-%m-%d")
found, day = {}, d0
while day <= d1:
    for x in nr.result_rows(nr.fetch_day(day.replace(tzinfo=nr.IST))):
        if x["symbol"].upper() in SYMS: found.setdefault(x["symbol"].upper(), x)
    day += timedelta(days=1)
sess = nr.sess()
for sym in SYMS:
    x = found.get(sym)
    print("=====", sym, x and x.get("attchmntFile"), flush=True)
    if not x: continue
    c = sess.get(x["attchmntFile"], headers={"Referer": nr.REF}, timeout=60).content
    small = pc.trim_pdf(c) if len(c) > 1_000_000 else c
    out, err = rr.read_pdf(small, x.get("attchmntText") or "", 131)
    if out is None and "no quarter columns" in (err or ""):
        out, err = rr.read_pdf(small, x.get("attchmntText") or "", 131, allow_half=True)
    print("READ err:", (err or "")[:300])
    if out:
        print("unit", out.get("unit"), "cols", out.get("quarter_end_columns"), "ocr", out.get("_ocr"), "half", out.get("_half"))
        for b in ("consolidated", "standalone"):
            d = out.get(b)
            if isinstance(d, dict):
                print(" ", b, {k: d.get(k) for k in ("revenue", "other_income", "total_income", "total_expenses", "pbt", "tax", "pat", "eps") if d.get(k)})
    for idx in ("equities", "sme"):
        try:
            r = sess.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=30)
            data = r.json().get("data", []) if r.status_code == 200 and r.text.strip() else []
        except Exception:
            data = []
        if data: break
    for y in data:
        if "Financial" in (y.get("type") or "") and y.get("xbrl") not in (None, "None") and str(y.get("qe_Date") or "").lower().startswith("30-sep-2026"):
            try:
                m = fd.parse_xbrl(sess.get(y["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=45).text)
            except Exception as e:
                m = repr(e)[:80]
            print("  XBRL", y.get("consolidated"), y.get("creation_Date"), {k: v for k, v in (m or {}).items() if k in ("revenue", "income", "total_income", "pbt", "pat", "eps", "expenses")} if isinstance(m, dict) else m)
