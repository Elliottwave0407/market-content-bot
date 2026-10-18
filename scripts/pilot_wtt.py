"""Walk-the-talk step A (dry run): find official transcripts on NSE, extract forward-looking promises with verified quotes."""
import os, sys, re, io, json, time, traceback
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
import fin_data as fd
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

JQ = """You are auditing whether management kept its promises. You get (A) promises made on one earnings call, (B) the company's FILED quarterly numbers and fiscal-year totals, (C) the transcripts of LATER calls.
For each promise decide a verdict using only B and C:
 delivered | delayed (done, but later than promised) | missed | partly | not_yet_due | unverifiable
Evidence must be one of: {"kind":"table","quarter":"Mar-26","metric":"ebitda_margin|revenue|pat|fy_revenue_growth","value":number} where value appears in B, or {"kind":"call","quote":"VERBATIM max 25 words from C"}. No outside knowledge. If B and C do not settle it, verdict is unverifiable.
Today is 18 Oct 2026. Return ONLY JSON: {"results":[{"i":index,"verdict":"","why":"one short line","evidence":{...}}]}"""
def table_text(rows):
    L = []; fy = {}
    for lab, m in rows:
        rev, eb = m.get("revenue"), m.get("ebitda")
        em = round(100 * eb / rev, 1) if rev and eb is not None else None
        L.append(f"{lab} revenue {rev} ebitda {eb} ebitda_margin {em} pat {m.get('pat')} ({m['basis']})")
        mon, yy = lab.split("-"); y = 2000 + int(yy); f = y + (1 if mon in ("Jan","Feb","Mar") else 0) - 0
        f = y if mon in ("Jan","Feb","Mar") else y + 1
        fy.setdefault(f, []).append(rev or 0)
    for f, v in sorted(fy.items()):
        if len(v) == 4: L.append(f"FY{f} revenue total {round(sum(v), 2)}")
    return "\n".join(L)
def judge(s, allp):
    rows = [(l, m) for l, m in fd.merged(s, SYM)]
    tt = table_text(rows); p("== FILED TABLE used by judge"); p(tt)
    tab_nums = set(re.findall(r"-?\d+\.?\d*", tt))
    tally = {}
    for i, c in enumerate(allp):
        if not c["promises"]: continue
        later = allp[i + 1:i + 3]
        if not later: p(f"{c['filed']} {c['q']}: no later calls yet"); continue
        ctext = "\n\n".join(f"[CALL FILED {x['filed']} {x['q']}]\n" + x["text"][:60000] for x in later)
        plist = json.dumps([{"i": k, "topic": pr.get("topic"), "promise": pr.get("promise"), "deadline": pr.get("deadline")} for k, pr in enumerate(c["promises"])])
        body = {"contents": [{"parts": [{"text": JQ + "\n\n(A) PROMISES from call filed " + c["filed"] + ":\n" + plist + "\n\n(B) TABLE:\n" + tt + "\n\n(C) LATER CALLS:\n" + ctext}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        res = None
        for t in range(4):
            r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=240)
            if r.status_code == 429 or r.status_code >= 500: time.sleep(20 * (t + 1)); continue
            try: res = json.loads(re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()))
            except Exception: res = None
            break
        if not res: p(c["filed"], "judge failed"); continue
        G = {" ".join(norm(ctext)[k:k + 4]) for k in range(len(norm(ctext)) - 3)}
        p(f"== JUDGED call {c['filed']} {c['q']}")
        for r_ in (res.get("results") or []):
            try: pr = c["promises"][int(r_.get("i"))]
            except Exception: continue
            ev = r_.get("evidence") or {}; v = r_.get("verdict"); ok = False
            if isinstance(ev, dict) and ev.get("kind") == "call": ok = quote_ok(ev.get("quote"), G)
            elif isinstance(ev, dict) and ev.get("kind") == "table":
                try: ok = str(round(float(ev.get("value")), 1)) in {str(round(float(n), 1)) for n in tab_nums} or str(ev.get("value")) in tab_nums
                except Exception: ok = False
            if v not in ("unverifiable", "not_yet_due") and not ok: v = "unverified-evidence"
            tally[v] = tally.get(v, 0) + 1
            p(f"  {v:>20} | {pr.get('promise')[:90]} | {str(r_.get('why'))[:100]}")
    p("== TALLY", json.dumps(tally))
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
        allp.append({"filed": d, "q": res.get("call_quarter"), "promises": ok, "text": txt})
    os.makedirs("out", exist_ok=True)
    judge(s, allp)
except Exception:
    p("ERR", traceback.format_exc()[-800:])
publish()
