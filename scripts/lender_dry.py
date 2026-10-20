"""DRY RUN: lender card through the live PDF path (BSE tables are empty for lenders). Env CODES (BSE scrip codes; default SBICARD, LICHSGFIN, POONAWALLA), FROM (default 2026-07-01)."""
import os, sys, json, tempfile, time, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
import results_fetcher as rf, card, pdf_card as pc, nse_results as nse
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sym2code = {v: k for k, v in json.load(open(os.path.join(root, "state", "symbols.json")))["m"].items()}
code2sym = {v: k for k, v in sym2code.items()}
codes = [x.strip() for x in (os.environ.get("CODES") or "").split(",") if x.strip()] or [sym2code[s] for s in ("SBICARD", "LICHSGFIN", "POONAWALLA")]
since = datetime.strptime(os.environ.get("FROM") or "2026-07-01", "%Y-%m-%d")
os.makedirs("out", exist_ok=True)
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for code in codes:
        rows = []
        for t in range(4):
            try: rows = b.announcements(scripcode=code, from_date=since, to_date=datetime.now(), category="Result").get("Table", []); break
            except Exception: time.sleep(5)
        rows = [r for r in rows if r.get("ATTACHMENTNAME")]
        if not rows: p(code, "no result PDF"); continue
        r = sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[-1]
        name = r.get("SLONGNAME") or code
        content = b""
        for folder in ("AttachLive", "AttachHis"):
            try: rr = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{r['ATTACHMENTNAME']}", headers=pc.UA, timeout=45)
            except Exception: continue
            if rr.content[:4] == b"%PDF": content = rr.content; break
        res, why = nse.read_card(content, name, bse=b, code=code) if content else (None, "PDF not downloadable")
        p(code, code2sym.get(code), name, str(r.get("NEWS_DT"))[:10], "->", why)
        if not res: continue
        fins = [round((x["m"] or {}).get("fin") or 0) for x in res["quarters"]]
        tk = f"NSE {code2sym.get(code)}"
        v = card.render(name, tk, res["basis"], res["quarters"], f"out/lender_{code2sym.get(code)}_{res['quarters'][0]['q']}.png", yprev=res.get("yprev"))
        p("  basis", res["basis"], "fin (Rs mn) by column", fins, "kind", card.fin_kind(tk), "verdict", v)
publish()
