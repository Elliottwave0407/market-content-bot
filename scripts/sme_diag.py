"""DIAGNOSTIC (posts nothing): why do these SME half-yearly filings end without a card? One read per company, reason saved after each.
Env: CODES, FROM (YYYY-MM-DD). Writes store/sme_diag/result.json."""
import os, sys, json, time, tempfile, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("PDF_TRIES", "1")
import pdf_card as pc, sme_half as sh
from bse import BSE
codes = [x.strip() for x in os.environ["CODES"].split(",") if x.strip()]
since = datetime.strptime(os.environ.get("FROM") or "2026-10-15", "%Y-%m-%d")
os.makedirs("store/sme_diag", exist_ok=True)
OUT = "store/sme_diag/result.json"
try: res = json.load(open(OUT))
except Exception: res = {}
key = pc.geminikey()
CHK = []
_orig = sh.sme_ok
def _spy(d, i):
    ok = _orig(d, i)
    CHK.append({"col": i, "ok": ok, **{x: pc.val(d, x, i) for x in ("revenue", "total_income", "total_expenses", "exceptional_items", "finance_costs", "pbt", "tax", "pat")}})
    return ok
sh.sme_ok = _spy
t0 = time.time()
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for c in codes:
        if time.time() - t0 > 30 * 60: break
        if c in res and res[c].get("why") not in ("error",) and not os.environ.get("REDO"): continue
        rec = {"code": c}
        try:
            rows = b.announcements(scripcode=c, from_date=since, to_date=datetime.now(), category="Result").get("Table", [])
            rows = [r for r in rows if r.get("ATTACHMENTNAME")]
            if not rows: rec["why"] = "no result PDF in window"
            else:
                r = sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[-1]
                rec["name"] = r.get("SLONGNAME"); rec["date"] = str(r.get("NEWS_DT"))[:10]
                content = b""
                for folder in ("AttachLive", "AttachHis"):
                    try: rr = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{r['ATTACHMENTNAME']}", headers=pc.UA, timeout=45)
                    except Exception: continue
                    if rr.content[:4] == b"%PDF": content = rr.content; break
                rec["bytes"] = len(content)
                if not content: rec["why"] = "PDF not downloadable"
                else:
                    try: rec["text_chars"] = len(pc.pdf_text(content)) if hasattr(pc, "pdf_text") else None
                    except Exception: rec["text_chars"] = None
                    CHK.clear()
                    out, why = sh.read_half_card(content, key, rec["name"] or c)
                    rec["checks"] = list(CHK)
                    rec["why"] = "ok" if out else why
                    if out: rec["basis"] = out["basis"]
        except Exception as e:
            rec["why"] = "error"; rec["err"] = repr(e)[:80]
        res[c] = rec
        print(rec, flush=True)
        json.dump(res, open(OUT, "w"), indent=0)
