"""DRY RUN ONLY (never sends): half-yearly result card for BSE-SME companies, read from the filing PDF.
Columns are: current half-year | preceding half-year | same half-year last year. Labels are half-year ends only (Mar / Sep).
Env: CODES (BSE scrip codes), FROM (YYYY-MM-DD, default 2025-10-01), GEMINI_API_KEY."""
import os, sys, tempfile, time, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import gemini_read as gr, pdf_card as pc, results_fetcher as rf, card
HALF = """You are reading an Indian SME-listed company's HALF-YEARLY financial results filing (PDF, may be scanned).
Extract the 'Statement of Audited/Unaudited Financial Results' table. Return ONLY JSON:
{"unit":"lakh|crore|million|thousand|actual",
 "quarter_end_columns":["<current half-year end date>","<preceding half-year end date>","<same half-year end date last year>"],
 "column_headings":["<exact heading text printed above column c>","<heading above p>","<heading above y>"],
 "consolidated": {"revenue":[c,p,y],"other_income":[c,p,y],"total_income":[c,p,y],"total_expenses":[c,p,y],"finance_costs":[c,p,y],"depreciation":[c,p,y],"pbt":[c,p,y],"tax":[c,p,y],"pat":[c,p,y],"eps":[c,p,y]} or null,
 "standalone": {same keys} or null}
Rules: c = the current HALF-YEAR column (six months), p = the immediately preceding half-year column, y = the same half-year one year earlier. Use only half-year columns; ignore full-year ('year ended') columns. If the filing shows 'Half year ended 30.09.2025 | Half year ended 31.03.2025 | Half year ended 30.09.2024', those are c, p, y.
revenue = 'Revenue from operations' (total, incl. other operating income). pbt = profit before tax (after exceptional items). pat = net profit/(loss) for the period (after tax).
Numbers exactly as printed, in the printed unit; negatives for losses. Use null for any value not present. Do not compute or guess."""
def sme_ok(d, i):
    """SME statements: total income - expenses must equal PBT; PAT must be sane versus PBT (tax lines often exclude deferred tax, so PBT - tax is NOT required to equal PAT)."""
    ti, ex, pbt, pat = (pc.val(d, x, i) for x in ("total_income", "total_expenses", "pbt", "pat"))
    if None in (ti, ex, pbt, pat): return False
    if abs((ti - ex) - pbt) > max(1.5, 0.002 * max(abs(ti), abs(ex))): return False
    if pbt > 0 and not (-0.3 * pbt <= pat <= 1.1 * pbt): return False
    if pbt <= 0 and pat > 0.5 * abs(pbt) + 1.5: return False
    return True

def read_half_card(content, key, name=""):
    """-> (dict(basis, q, quarters), 'ok') or (None, reason). Reads a half-yearly results PDF (SME). Columns: current half | preceding half | same half last year."""
    out, err = gr.read_pdf(key, pc.MODEL, content, tries=int(os.environ.get("PDF_TRIES", "3")), timeout=120, prompt=HALF)
    if out is None: return None, "pdf read failed: " + str(err)[:70]
    k = pc.K.get(str(out.get("unit", "")).lower()); cols = out.get("quarter_end_columns") or []
    p("  columns read:", cols, out.get("column_headings"), "unit", out.get("unit"))
    qe = [pc.parse_qend(x) for x in cols[:3]]
    if not k or len(qe) < 3 or None in qe: return None, "unit or columns unreadable"
    mon = [x[0] * 12 + x[1] for x in qe]
    swapped = (mon[0] - mon[1], mon[0] - mon[2]) == (12, 6)      # filing lists current | same half last year | preceding half (e.g. Aptus Pharma)
    if swapped:
        for b_ in ("consolidated", "standalone"):
            d_ = out.get(b_)
            if isinstance(d_, dict):
                for kk, vv in list(d_.items()):
                    if isinstance(vv, list) and len(vv) >= 3: vv[1], vv[2] = vv[2], vv[1]
        mon[1], mon[2] = mon[2], mon[1]
    if not (mon[0] - mon[1] == 6 and mon[0] - mon[2] == 12): return None, "not a half-yearly filing (columns are not 6 and 12 months apart)"
    if qe[0][1] not in (3, 9): return None, "half-year end month is not Mar/Sep"
    q = rf.qcode(qe[0][0], qe[0][1])
    cons = out.get("consolidated")
    has_cons = isinstance(cons, dict) and pc.val(cons, "revenue", 0) is not None and pc.val(cons, "pat", 0) is not None
    for basis in (("consolidated", "standalone") if has_cons else ("standalone",)):
        d = out.get(basis)
        if not isinstance(d, dict) or pc.val(d, "revenue", 0) is None or pc.val(d, "pat", 0) is None: continue
        oks = [sme_ok(d, i) for i in range(3)]
        p(" ", name, basis, "arithmetic by column (current, previous, year-ago):", oks)
        if not all(oks): return None, f"{basis} figures failed arithmetic checks"
        cur, prev, yago = (pc.to_m(d, i, k) for i in range(3))
        if cur["revenue"] and prev["revenue"] and cur["revenue"] > 0 and prev["revenue"] > 0 and (cur["revenue"] / prev["revenue"] > 50 or prev["revenue"] / cur["revenue"] > 50): return None, "figures inconsistent with the previous half-year"
        empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
        if cur.get("ebitda") is None or prev.get("ebitda") is None or yago.get("ebitda") is None: return None, "operating profit not derivable (finance cost or expenses missing)"
        qs = [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 2), "m": prev}, {"q": " ", "m": empty}, {"q": " ", "m": empty}, {"q": rf.qlabel(q - 4), "m": yago}]
        return {"basis": basis, "q": q, "quarters": qs, "note": "arithmetic-checked"}, "ok"
    return None, "no usable statement"

if __name__ == "__main__":
    from bse import BSE
    codes = [x.strip() for x in (os.environ.get("CODES") or "").split(",") if x.strip()]
    since = datetime.strptime(os.environ.get("FROM") or "2026-01-01", "%Y-%m-%d")
    os.makedirs("out", exist_ok=True)
    key = pc.geminikey()
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for c in codes:
            rows = []
            for tries in range(4):
                try:
                    rows = b.announcements(scripcode=c, from_date=since, to_date=datetime.now(), category="Result").get("Table", []); break
                except Exception as e:
                    p(c, "announcements retry", tries, repr(e)[:50]); time.sleep(5 * (tries + 1))
            rows = [r for r in rows if r.get("ATTACHMENTNAME")]
            if not rows: p(c, "no result PDF"); continue
            r = sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[-1]
            name = r.get("SLONGNAME") or c
            p(c, name, str(r.get("NEWS_DT"))[:10], str(r.get("HEADLINE") or "")[:80])
            content = b""
            for folder in ("AttachLive", "AttachHis"):
                try: rr = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{r['ATTACHMENTNAME']}", headers=pc.UA, timeout=45)
                except Exception: continue
                if rr.content[:4] == b"%PDF": content = rr.content; break
            if not content: p("  PDF not downloadable"); continue
            res, why = read_half_card(content, key, name)
            if not res: p("  not usable:", why); continue
            png = f"out/sme_{name.replace(' ', '_')[:20]}_{rf.qlabel(res['q'])}_{res['basis']}.png"
            v = card.render(name, c, res["basis"], res["quarters"], png, "", half=True)
            p("  rendered", png, "verdict", v)
    publish()
