"""Walk-the-talk step A (dry run): find official transcripts on NSE, extract forward-looking promises with verified quotes."""
import os, sys, re, io, json, time, traceback
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E"); FROM = os.environ.get("FROM_DATE", "01-06-2023")
Q = """You read an Indian company's earnings-call transcript. Extract ONLY forward-looking commitments MANAGEMENT made that can later be checked: numeric targets (margin, revenue, capex, capacity, utilisation, order book), timelines (go-live, commissioning, launch), fund-raise or debt plans, and promises about disclosures. Skip vague hopes ("we are optimistic"). Return ONLY JSON:
{"call_quarter":"quarter being discussed, as spoken","promises":[{"topic":"margin|revenue|capex|capacity|launch|funding|customer|other","promise":"plain English, numbers exactly as spoken","deadline":"when it was due, as spoken, or null","quote":"VERBATIM from transcript, max 25 words"}]}
Max 8 promises, the most checkable first. If management gave no checkable commitments, return an empty list."""
def call(text):
    body = {"contents": [{"parts": [{"text": Q + "\n\nTRANSCRIPT:\n" + text[:300000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(4):
        r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=240)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (i + 1)); continue
        if r.status_code != 200: return None
        try:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", t.strip()))
        except Exception: return None
    return None
try:
    s = nse.sess(); H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
    j = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": SYM, "from_date": FROM, "to_date": "18-10-2026"}, headers=H, timeout=60).json()
    tr = {}
    for x in j:
        t = (x.get("attchmntText") or "") + " " + (x.get("desc") or "")
        f = x.get("attchmntFile") or ""
        if "Analysts/Institutional" in (x.get("desc") or "") and "transcript" in t.lower() and f.lower().endswith(".pdf") and "intimation" not in f.lower():
            tr[f] = (x.get("an_dt") or "")[:11]
    items = sorted(tr.items(), key=lambda kv: __import__("datetime").datetime.strptime(kv[1], "%d-%b-%Y"))
    p("transcripts found:", len(items))
    allp = []
    for f, d in items:
        try:
            r = s.get(f, headers={"Referer": "https://www.nseindia.com/"}, timeout=90)
            from pypdf import PdfReader
            txt = " ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:
            p(d, "download/parse failed", repr(e)[:60]); continue
        if len(txt) < 5000:
            p(d, "text too short (scanned?)", len(txt)); continue
        res = call(txt)
        if not res: p(d, "extract failed"); continue
        G = {" ".join(norm(txt)[i:i + 4]) for i in range(len(norm(txt)) - 3)}
        ok = []
        for pr in (res.get("promises") or []):
            if isinstance(pr, dict) and quote_ok(pr.get("quote"), G): ok.append(pr)
        p(f"== {d} | {res.get('call_quarter')} | {len(ok)}/{len(res.get('promises') or [])} verified | chars {len(txt)}")
        for pr in ok:
            p(f"  [{pr.get('topic')}] {pr.get('promise')} | due: {pr.get('deadline')} | \"{(pr.get('quote') or '')[:130]}\"")
        allp.append({"filed": d, "q": res.get("call_quarter"), "promises": ok})
    os.makedirs("out", exist_ok=True)
    json.dump(allp, open("out/wtt_promises.json", "w"))
except Exception:
    p("ERR", traceback.format_exc()[-800:])
publish()
