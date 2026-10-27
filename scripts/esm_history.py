"""Backfill ESM history from NSE's daily 'Applicability of Enhanced Surveillance Measure (ESM)' circulars (ZIP with Annexure.xlsx): every entry to Stage I, Stage I->II, Stage II->I and exclusion since Jul 2025, with effective dates.
Output: store/esm_history/events.json  [{eff, ev, sym, isin, name, circ}]  and processed.json (circular numbers done, so reruns only fetch new ones). Read-only on the exchange; posts nothing."""
import os, sys, io, re, json, time, zipfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
from datetime import datetime
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}
OUT = "store/esm_history"; os.makedirs(OUT, exist_ok=True)
BUDGET = float(os.environ.get("BUDGET_MIN", "35")) * 60; T0 = time.time()
FROM = os.environ.get("FROM_DATE", "01-07-2025")

def kind(h):
    t = h.lower()
    if "excluded" in t or "exclusion" in t: return "exit"
    if re.search(r"stage\s*-?\s*ii\s+to\s+stage\s*-?\s*i\b", t): return "II_to_I"
    if re.search(r"stage\s*-?\s*i\s+to\s+stage\s*-?\s*ii", t): return "I_to_II"
    if "shortlisted" in t and re.search(r"stage\s*-?\s*i\b", t): return "enter_I"
    return None

def eff_date(h):
    m = re.search(r"w\.e\.f\.?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", h)
    if m:
        try: return datetime.strptime(re.sub(r"\s+", " ", m.group(1)), "%B %d, %Y").strftime("%Y-%m-%d")
        except Exception: pass
    return None

try:
    import openpyxl
    try: events = json.load(open(f"{OUT}/events.json")); done = set(json.load(open(f"{OUT}/processed.json")))
    except Exception: events, done = [], set()
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25)
    rows = []
    today = datetime.utcnow().strftime("%d-%m-%Y")
    y1, y2 = FROM, today
    parts = [(y1, "31-12-2025")] if y1.endswith("2025") else []
    parts.append(("01-01-2026" if y1.endswith("2025") else y1, y2))
    for a, b in parts:
        r = s.get(f"https://www.nseindia.com/api/circulars?fromDate={a}&toDate={b}&department=SURVEILLANCE", headers={"Referer": "https://www.nseindia.com/resources/exchange-communication-circulars"}, timeout=60)
        rows += r.json().get("data", []) if r.status_code == 200 else []
    esm = sorted([x for x in rows if "Applicability of Enhanced Surveillance Measure" in (x.get("sub") or "")], key=lambda x: x.get("cirDate", ""))
    todo = [x for x in esm if x["circDisplayNo"] not in done]
    p("ESM applicability circulars:", len(esm), "| to process:", len(todo))
    bad = 0
    for x in todo:
        if time.time() - T0 > BUDGET: break
        try:
            r = requests.get(x["circFilelink"], headers=UA, timeout=60)
            z = zipfile.ZipFile(io.BytesIO(r.content)) if r.content[:2] == b"PK" and x["circFilelink"].endswith(".zip") else None
            xl = None
            if z:
                nm = [n for n in z.namelist() if n.lower().endswith((".xlsx",))]
                xl = z.read(nm[0]) if nm else None
            if xl is None: bad += 1; done.add(x["circDisplayNo"]); continue
            wb = openpyxl.load_workbook(io.BytesIO(xl), read_only=True)
            cur, eff = None, None
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    c0 = row[0]
                    if isinstance(c0, str) and "list of securities" in c0.lower():
                        cur, eff = kind(c0), eff_date(c0) or datetime.strptime(x["cirDate"], "%Y%m%d").strftime("%Y-%m-%d"); continue
                    if cur and isinstance(c0, (int, float)) and row[1]:
                        events.append({"eff": eff, "ev": cur, "sym": str(row[1]).strip(), "isin": str(row[3] or "").strip(), "name": str(row[2] or "").replace("*", "").strip(), "circ": x["circDisplayNo"]})
            done.add(x["circDisplayNo"])
        except Exception as e:
            p("circular error", x.get("circDisplayNo"), repr(e)[:80]); bad += 1
        time.sleep(0.4)
    json.dump(events, open(f"{OUT}/events.json", "w"), separators=(",", ":")); json.dump(sorted(done), open(f"{OUT}/processed.json", "w"))
    import collections
    p("events:", len(events), dict(collections.Counter(e["ev"] for e in events)), "| unreadable:", bad, "| processed:", len(done), "of", len(esm))
    p("first/last effective:", min((e["eff"] for e in events), default=None), max((e["eff"] for e in events), default=None))
except Exception:
    p("ERROR", traceback.format_exc()[-700:])
publish()
