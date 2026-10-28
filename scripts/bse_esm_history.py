"""BSE ESM history + current list. Each BSE 'Enhanced Surveillance Measure (ESM)' notice PDF links an Annexure xlsx (Annexure III = consolidated list with stage).
For every notice since FROM_DATE (chronological) the consolidated list is diffed against the previous one: enter_I / I_to_II / II_to_I / exit events with the notice date.
Output: store/esm_history/bse_events.json, bse_processed.json, store/esm/bse_latest.json (current list). Read-only on the exchange; posts nothing."""
import os, sys, io, re, json, time, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests, pypdf, openpyxl
from datetime import datetime, timedelta
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.bseindia.com/"}
OUT = "store/esm_history"; os.makedirs(OUT, exist_ok=True); os.makedirs("store/esm", exist_ok=True)
BUDGET = float(os.environ.get("BUDGET_MIN", "40")) * 60; T0 = time.time()
FROM = datetime.strptime((os.environ.get("FROM_DATE") or "2025-07-01"), "%Y-%m-%d")

def get(u, tries=3):
    for i in range(tries):
        try:
            r = requests.get(u, headers=H, timeout=60)
            if r.status_code == 200: return r.content
        except Exception: pass
        time.sleep(3)
    return None

def link_of(pdf):
    rd = pypdf.PdfReader(io.BytesIO(pdf))
    for pg in rd.pages:
        for a in (pg.get("/Annots") or []):
            act = a.get_object().get("/A")
            if act is not None:
                u = act.get_object().get("/URI")
                if u and "Annexure" in str(u): return str(u)
    return None

def sheet_rows(xl):
    if xl[:2] == b"PK":
        wb = openpyxl.load_workbook(io.BytesIO(xl), data_only=True)
        ws = None
        for w in wb.worksheets:
            if "III" in w.title: ws = w
        if ws is None: ws = wb.worksheets[-1]
        return list(ws.iter_rows(values_only=True))
    import xlrd
    wb = xlrd.open_workbook(file_contents=xl)
    sh = None
    for i in range(wb.nsheets):
        if "III" in wb.sheet_by_index(i).name: sh = wb.sheet_by_index(i)
    if sh is None: sh = wb.sheet_by_index(wb.nsheets - 1)
    return [[(str(int(v)) if isinstance(v, float) and v == int(v) else v) for v in sh.row_values(r)] for r in range(sh.nrows)]

def consolidated(xl):
    res = {}
    for row in sheet_rows(xl):
        c = [str(x).strip() if x is not None else "" for x in row]
        if len(c) >= 5 and c[1].isdigit() and c[2].startswith("INE") and c[4] in ("I", "II"):
            res[c[2]] = {"code": c[1], "name": c[3].rstrip("*").strip(), "st": c[4], "nse": c[3].endswith("*")}
    return res

try:
    from bse import BSE
    try: events = json.load(open(f"{OUT}/bse_events.json")); done = json.load(open(f"{OUT}/bse_processed.json"))
    except Exception: events, done = [], {}
    notices = {}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        a = FROM
        while a < datetime.now():
            z = min(a + timedelta(days=30), datetime.now())
            for _t in range(3):
                try:
                    r = b.circulars(from_date=a, to_date=z, subject="ESM")
                    rows = r.get("Table", r) if isinstance(r, dict) else r
                    for x in rows or []:
                        n = x.get("Notice_No")
                        if n and "Enhanced Surveillance" in (x.get("Subject") or x.get("SUBJECT") or "Enhanced Surveillance"): notices[n] = x
                    break
                except Exception as e: p("circulars retry", type(e).__name__); time.sleep(5)
            a = z + timedelta(days=1)
    order = sorted(notices)
    p("ESM notices found:", len(order), "| already done:", len(done))
    prev = None
    # previous list = list of the last processed notice (kept in bse_latest.json only for the newest); rebuild chain from scratch when starting empty
    if done and os.path.exists("store/esm/bse_latest.json"): prev = json.load(open("store/esm/bse_latest.json"))["list"]; prev_no = json.load(open("store/esm/bse_latest.json"))["notice"]
    else: prev_no = None
    new = 0; fail = []
    for n in order:
        if n in done: continue
        if time.time() - T0 > BUDGET: p("budget reached"); break
        pdf = get(f"https://www.bseindia.com/downloads/UploadDocs/Notices/{n}/{n}.pdf")
        lk = link_of(pdf) if pdf and pdf[:4] == b"%PDF" else None
        xl = get(lk) if lk else None
        if not xl: fail.append(n); done[n] = "fail"; continue
        try: cur = consolidated(xl)
        except Exception as e:
            p("unreadable annexure", n, type(e).__name__, xl[:4]); cur = None
        if not cur: fail.append(n); done[n] = "empty"; continue
        d = datetime.strptime(n[:8], "%Y%m%d").strftime("%Y-%m-%d")
        if prev is not None:
            for i, v in cur.items():
                o = prev.get(i)
                if o is None: events.append({"d": d, "ev": "enter_I" if v["st"] == "I" else "enter_II", "isin": i, "code": v["code"], "name": v["name"], "n": n})
                elif o["st"] != v["st"]: events.append({"d": d, "ev": "I_to_II" if v["st"] == "II" else "II_to_I", "isin": i, "code": v["code"], "name": v["name"], "n": n})
            for i, o in prev.items():
                if i not in cur: events.append({"d": d, "ev": "exit", "isin": i, "code": o["code"], "name": o["name"], "n": n})
        prev = cur; prev_no = n; done[n] = len(cur); new += 1
    json.dump(events, open(f"{OUT}/bse_events.json", "w")); json.dump(done, open(f"{OUT}/bse_processed.json", "w"))
    if prev: json.dump({"notice": prev_no, "list": prev}, open("store/esm/bse_latest.json", "w"))
    p("new notices processed:", new, "| failed:", fail[:10], "| events:", len(events))
    if prev:
        mc = json.load(open("store/mcap/mcap.json"))
        sme = [i for i in prev if (mc.get(i) or {}).get("g") in ("M", "MT", "MS")]
        nse_dual = sum(1 for v in prev.values() if v["nse"])
        p("current list", prev_no, "| total", len(prev), "| stage I", sum(1 for v in prev.values() if v["st"] == "I"), "| stage II", sum(1 for v in prev.values() if v["st"] == "II"), "| BSE SME groups", len(sme), "| also on NSE (*)", nse_dual)
        import collections
        p("by BSE group:", dict(collections.Counter((mc.get(i) or {}).get("g", "?") for i in prev)))
        c = collections.Counter(e["ev"] for e in events); p("event counts:", dict(c))
except Exception: p("ERROR", traceback.format_exc()[-700:])
publish()
