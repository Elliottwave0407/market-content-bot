"""DRY RUN ONLY (never sends): half-yearly result card for BSE-SME companies, read from the filing PDF.
Columns are: current half-year | preceding half-year | same half-year last year. Labels are half-year ends only (Mar / Sep).
Env: CODES (BSE scrip codes), FROM (YYYY-MM-DD, default 2025-10-01), GEMINI_API_KEY."""
import os, sys, tempfile, time, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
import gemini_read as gr, pdf_card as pc, results_fetcher as rf, card, nse_results as nse
HALF = """You are reading an Indian SME-listed company's HALF-YEARLY financial results filing (PDF, may be scanned).
Extract the 'Statement of Audited/Unaudited Financial Results' table. Return ONLY JSON:
{"unit":"lakh|crore|million|thousand|actual",
 "quarter_end_columns":["<current half-year end date>","<preceding half-year end date>","<same half-year end date last year>"],
 "consolidated": {"revenue":[c,p,y],"other_income":[c,p,y],"total_income":[c,p,y],"total_expenses":[c,p,y],"finance_costs":[c,p,y],"depreciation":[c,p,y],"pbt":[c,p,y],"tax":[c,p,y],"pat":[c,p,y],"eps":[c,p,y]} or null,
 "standalone": {same keys} or null}
Rules: c = the current HALF-YEAR column (six months), p = the immediately preceding half-year column, y = the same half-year one year earlier. Use only half-year columns; ignore full-year ('year ended') columns. If the filing shows 'Half year ended 30.09.2025 | Half year ended 31.03.2025 | Half year ended 30.09.2024', those are c, p, y.
revenue = 'Revenue from operations' (total, incl. other operating income). pbt = profit before tax (after exceptional items). pat = net profit/(loss) for the period (after tax).
Numbers exactly as printed, in the printed unit; negatives for losses. Use null for any value not present. Do not compute or guess."""
gr.PROMPT = HALF
codes = [x.strip() for x in (os.environ.get("CODES") or "").split(",") if x.strip()]
since = datetime.strptime(os.environ.get("FROM") or "2025-10-01", "%Y-%m-%d")
os.makedirs("out", exist_ok=True)
key = pc.geminikey()
def hlabel(d):  # 'dd-mm-yyyy' style date -> Mar/Sep label; returns (label, year, month)
    pq = pc.parse_qend(d); return pq
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for c in codes:
        try:
            rows = b.announcements(scripcode=c, from_date=since, to_date=datetime.now(), category="Result").get("Table", [])
        except Exception as e:
            p(c, "announcements failed", repr(e)[:60]); continue
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
        out, err = gr.read_pdf(key, pc.MODEL, content, tries=4, timeout=120)
        if out is None: p("  read failed", str(err)[:80]); continue
        k = pc.K.get(str(out.get("unit", "")).lower()); cols = out.get("quarter_end_columns") or []
        p("  unit", out.get("unit"), "columns", cols)
        qe = [pc.parse_qend(x) for x in cols[:3]]
        if not k or len(qe) < 3 or None in qe: p("  unit/columns unreadable"); continue
        mon = [x[0] * 12 + x[1] for x in qe]
        if not (mon[0] - mon[1] == 6 and mon[0] - mon[2] == 12): p("  columns are not current/previous half/year-ago half:", mon); continue
        if qe[0][1] not in (3, 9): p("  half-year end month is not Mar/Sep:", qe[0]); continue
        q = rf.qcode(qe[0][0], qe[0][1])
        for basis in ("consolidated", "standalone"):
            d = out.get(basis)
            if not isinstance(d, dict) or pc.val(d, "revenue", 0) is None or pc.val(d, "pat", 0) is None: continue
            oks = [nse.arith_col(d, i) for i in range(3)]
            p(" ", basis, "arithmetic by column:", oks)
            if not all(oks): p("  failed arithmetic checks"); break
            cur, prev, yago = (pc.to_m(d, i, k) for i in range(3))
            empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
            qs = [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 2), "m": prev}, {"q": " ", "m": empty}, {"q": " ", "m": empty}, {"q": rf.qlabel(q - 4), "m": yago}]
            png = f"out/sme_{name.replace(' ', '_')[:20]}_{rf.qlabel(q)}_{basis}.png"
            card.render(name, c, basis, qs, png, "", half=True)
            rt = card.rating(qs, basis)
            p("  rendered", png, "verdict", rt, {x: (round(v, 1) if isinstance(v, float) else v) for x, v in cur.items() if x in ("revenue", "ebitda", "pat")})
            break
publish()
