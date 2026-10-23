"""Read-only validation of the rule-based PDF reader against real filings: parse rate, arithmetic pass rate, and agreement with BSE's own XBRL numbers. Posts nothing."""
import os, sys, time, collections
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
from bse import BSE
import rule_read as rr
import pdf_card as pc
import results_fetcher as rf

DAYS = [int(x) for x in os.environ.get("DAYS", "1,2,3").split(",")]
MAXN = int(os.environ.get("MAXN", "150"))
UA = pc.UA

def filings(bse):
    rows = []
    for back in DAYS:
        d = datetime.now() - timedelta(days=back)
        pg, seen = 1, 0
        while pg <= 40:
            data = bse.announcements(page_no=pg, from_date=d, to_date=d)
            t = data.get("Table", [])
            if not t: break
            seen += len(t)
            rows += [r for r in t if r.get("CATEGORYNAME") == "Result" and r.get("ATTACHMENTNAME")]
            if seen >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
            pg += 1
    return rows[:MAXN]

def get(rec):
    for folder in ("AttachLive", "AttachHis"):
        try:
            r = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{rec['ATTACHMENTNAME']}", headers=UA, timeout=45)
            if r.content[:4] == b"%PDF": return r.content
        except Exception:
            pass
    return None

def one(rec):
    t0 = time.time()
    c = get(rec)
    if not c: return rec, None, "download failed", 0
    small = pc.trim_pdf(c)
    hl = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
    try: qh = rf.expected_quarter(hl, datetime.fromisoformat(rec["NEWS_DT"][:19]))
    except Exception: qh = None
    out, err = rr.read_pdf(small, hint=hl, qhint=qh)
    if out is None and small is not c:
        out, err = rr.read_pdf(c, hint=hl, qhint=qh)
    return rec, out, err, time.time() - t0

def main():
    with BSE(download_folder="./") as bse:
        fl = filings(bse)
        p("filings with pdf:", len(fl))
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(one, fl))
        st = collections.Counter(); bad = []
        for rec, out, err, dt in res:
            name = rec["SLONGNAME"][:28]
            if out is None:
                st["no_parse:" + str(err)[:40]] += 1; continue
            k = pc.K.get(str(out.get("unit")).lower())
            basis = "consolidated" if out.get("consolidated") else "standalone"
            d = out.get(basis)
            ok, n = pc.arith_ok(d)
            st["parsed"] += 1; st["arith_ok" if ok else "arith_fail"] += 1
            filed = datetime.fromisoformat(rec["NEWS_DT"][:19])
            q = None
            try:
                q = rf.expected_quarter((rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or ""), filed)
            except Exception: pass
            gt = None
            if q is not None and k:
                try: gt = rf.fetch(bse, str(rec["SCRIP_CD"]), rec["SLONGNAME"], basis, q)
                except Exception: gt = None
            cur = pc.to_m(d, 0, k) if k else {}
            if gt and gt.get("revenue") is not None and cur.get("revenue") is not None:
                same = pc.close(cur["revenue"], gt["revenue"]) and (gt.get("pat") is None or cur.get("pat") is None or abs(cur["pat"] - gt["pat"]) <= max(1.0, 0.03 * abs(gt["pat"])))
                st["gt_agree" if same else "gt_DISAGREE"] += 1
                if not same: bad.append(f"{name} {basis} unit={out['unit']} dates={out['quarter_end_columns']} rule rev {cur['revenue']} pat {cur['pat']} | bse rev {gt['revenue']} pat {gt['pat']} | arith {ok}")
            else:
                st["gt_none"] += 1
            if not ok: bad.append(f"ARITH {name} {basis} " + ", ".join(f"{x}={pc.val(d, x, 0)}" for x in ("revenue", "total_income", "total_expenses", "pbt", "tax", "pat")))
        p("SUMMARY", dict(st))
        for b in bad[:60]: p(b)
        ts = sorted(dt for _, o, _, dt in res if o)
        if ts: p("parse+download seconds median", f"{ts[len(ts)//2]:.1f}", "max", f"{ts[-1]:.1f}")
    publish()

if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; p("ERROR", traceback.format_exc()[-1500:]); publish()
