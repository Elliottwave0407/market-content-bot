"""Walk-the-talk step B (dry run): extract promises per official transcript, then judge each against filed numbers and later calls.
Every verdict needs evidence: a verbatim quote found in a later transcript, or numbers found in the filed-numbers table. Otherwise 'unverifiable'."""
import os, sys, re, io, json, time, traceback
from datetime import datetime
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E"); FROM = os.environ.get("FROM_DATE", "01-06-2023")
QX = """You read an Indian company's earnings-call transcript. Extract ONLY forward-looking commitments MANAGEMENT made that can later be checked: numeric targets (margin, revenue, capex, capacity, utilisation, order book), timelines (go-live, commissioning, launch), fund-raise or debt plans. Skip vague hopes. Return ONLY JSON:
{"promises":[{"topic":"margin|revenue|capex|capacity|launch|funding|customer|other","promise":"plain English, numbers exactly as spoken","deadline":"when due, as spoken, or null","quote":"VERBATIM from transcript, max 25 words"}]}
Max 8 promises, most checkable first."""
QJ = """You are auditing whether management kept its promises. CALL DATE: {date}. PROMISES made on that call (numbered):
{plist}

FILED NUMBERS (Rs Cr, from exchange filings; quarter labels are quarter-end months):
{table}

LATER CALL TRANSCRIPTS (text follows after the marker) may confirm or contradict timelines.
For each promise return a verdict: "delivered" (met in time), "delayed" (met but later than promised), "missed" (not met), "partly", or "unverifiable" (not enough evidence).
Return ONLY JSON: {{"verdicts":[{{"n":1,"verdict":"","evidence_type":"quote|table","evidence":"if quote: VERBATIM sentence from the LATER transcripts (max 30 words); if table: the exact figures used, e.g. 'Mar-26 EBITDA margin 60.7%'","note":"one short line"}}]}}
Rules: never use outside knowledge. Use only the filed numbers or the later transcripts. A later-call quote can prove a delay (e.g. it says something is still not live). If the due date has not yet passed, verdict is "unverifiable"."""
def gj(prompt, text):
    body = {"contents": [{"parts": [{"text": prompt + "\n\nTEXT:\n" + text[:600000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(4):
        r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=300)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(25 * (i + 1)); continue
        if r.status_code != 200: return None
        try:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", t.strip()))
        except Exception: return None
    return None
def grams(t):
    n = norm(t); return {" ".join(n[i:i + 4]) for i in range(len(n) - 3)}
def table_text(rows):
    L = []
    for lab, m in rows:
        rev, eb, pat = m.get("revenue"), m.get("ebitda"), m.get("pat")
        em = round(100 * eb / rev, 1) if rev and eb is not None else None
        L.append(f"{lab}: revenue {rev}, monthly avg revenue {round(rev/3,1) if rev else None}, EBITDA {eb}, EBITDA margin {em}%, PAT {pat} ({m['basis']})")
    # fiscal years Apr-Mar
    fy = {}
    for lab, m in rows:
        d = datetime.strptime("01-" + lab, "%d-%b-%y"); y = d.year + (1 if d.month > 3 else 0)
        fy.setdefault(y, []).append(m)
    for y, ms in sorted(fy.items()):
        if len(ms) == 4:
            L.append(f"FY{str(y)[2:]} total: revenue {round(sum(x['revenue'] for x in ms),1)}, EBITDA {round(sum(x['ebitda'] for x in ms),1)}, PAT {round(sum(x['pat'] for x in ms),1)}")
    return "\n".join(L)
def nums(s): return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))]
try:
    s = nse.sess(); H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
    rows = fd.merged(s, SYM); TT = table_text(rows); TTN = nums(TT)
    j = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": SYM, "from_date": FROM, "to_date": "18-10-2026"}, headers=H, timeout=60).json()
    tr = {}
    for x in j:
        t = (x.get("attchmntText") or "") + " " + (x.get("desc") or ""); f = x.get("attchmntFile") or ""
        if "Analysts/Institutional" in (x.get("desc") or "") and "transcript" in t.lower() and f.lower().endswith(".pdf") and "intimation" not in f.lower():
            tr[f] = (x.get("an_dt") or "")[:11]
    items = sorted(tr.items(), key=lambda kv: datetime.strptime(kv[1], "%d-%b-%Y"))
    from pypdf import PdfReader
    docs = []
    for f, d in items:
        try:
            r = s.get(f, headers={"Referer": "https://www.nseindia.com/"}, timeout=90)
            txt = " ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
            if len(txt) > 5000: docs.append((d, txt))
        except Exception as e:
            p(d, "skip", repr(e)[:50])
    # dedupe near-identical (revised) transcripts filed within 3 days
    ded = []
    for d, t in docs:
        if ded and abs((datetime.strptime(d, "%d-%b-%Y") - datetime.strptime(ded[-1][0], "%d-%b-%Y")).days) <= 3 and t[:300] == ded[-1][1][:300]:
            continue
        ded.append((d, t))
    docs = ded
    p("transcripts:", len(docs)); tally = {}; ledger = []
    for i, (d, txt) in enumerate(docs):
        G = grams(txt)
        e = gj(QX, txt) or {}
        pr = [x for x in (e.get("promises") or []) if isinstance(x, dict) and quote_ok(x.get("quote"), G)]
        if not pr: p(d, "no verified promises"); continue
        later = docs[i + 1:i + 3]
        if not later:
            p(f"== {d}: {len(pr)} promises, no later call yet -> unverifiable (too recent)"); continue
        LG = grams(" ".join(t for _, t in later))
        plist = "\n".join(f"{k+1}. [{x.get('topic')}] {x.get('promise')} (due: {x.get('deadline')})" for k, x in enumerate(pr))
        v = gj(QJ.format(date=d, plist=plist, table=TT), "\n\n".join(f"--- LATER CALL filed {dd} ---\n{tt}" for dd, tt in later)) or {}
        p(f"== {d}: {len(pr)} promises")
        got = {x.get("n"): x for x in (v.get("verdicts") or []) if isinstance(x, dict)}
        for k, x in enumerate(pr):
            jv = got.get(k + 1) or {}
            verdict, et, ev = jv.get("verdict") or "unverifiable", jv.get("evidence_type"), jv.get("evidence") or ""
            ok = (et == "quote" and quote_ok(ev, LG)) or (et == "table" and nums(ev) and all(any(abs(a - b) <= 0.15 for b in TTN) for a in nums(ev)))
            if verdict != "unverifiable" and not ok:
                verdict = "unverifiable (evidence failed check)"
            tally[verdict] = tally.get(verdict, 0) + 1
            ledger.append({"date": d, "promise": x.get("promise"), "verdict": verdict})
            p(f"  {verdict.upper()[:14]:14} | {x.get('promise')[:95]} | due {x.get('deadline')} | {et}: {ev[:110]} | {jv.get('note','')[:80]}")
    p("TALLY", json.dumps(tally))
except Exception:
    p("ERR", traceback.format_exc()[-800:])
publish()
