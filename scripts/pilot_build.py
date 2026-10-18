"""Builds / refreshes one company's data store (dry run: posts nothing). Cached: only new transcripts are extracted;
verdicts are re-judged only when needed (JUDGE=1) so free-tier quota is not wasted."""
import os, sys, re, io, json, time, hashlib, traceback
from datetime import datetime
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd, store
src = open(os.path.join(os.path.dirname(__file__), "concall_scan.py")).read()
exec(src[src.index("KEY = "):src.index("DBG = []")])
exec(src[src.index("def norm"):src.index("def mcaps")])
SYM = os.environ.get("SYMBOL", "E2E").strip().upper(); CODE = os.environ.get("SCRIP", "").strip(); NAME = os.environ.get("CNAME", "").strip()
JUDGE = os.environ.get("JUDGE", "0") == "1"; FROM = os.environ.get("FROM_DATE", "01-06-2023")
NOW = datetime.utcnow().strftime("%Y-%m-%d")
EXTRACTOR = "v3"
QX = """You read an Indian company's earnings-call transcript. Extract ONLY firm forward-looking commitments MANAGEMENT made that can later be checked: numeric targets (margin, revenue, capex, capacity, utilisation, order book, run-rate), timelines (go-live, commissioning, launch), fund-raise or debt plans.
EXCLUDE only: pure hypotheticals ("in an ideal world", "if we had the money"), things management explicitly says are NOT a guidance/announcement, and statements about the past. Mark firmness "soft" for tentative language ("hopefully", "we would like to"), "firm" otherwise.
Return ONLY JSON: {"promises":[{"topic":"margin|revenue|capex|capacity|launch|funding|customer|other","promise":"plain English, numbers exactly as spoken","deadline":"when due, as spoken, or null","firmness":"firm|soft","quote":"VERBATIM from transcript, max 25 words"}]}
Max 8 promises, most checkable first."""
QJ = """You are auditing whether management kept its promises. CALL DATE: {date}. PROMISES made on that call (numbered):
{plist}

FILED NUMBERS (Rs Cr, exchange filings; labels are quarter-end months):
{table}

LATER CALL TRANSCRIPTS follow in the text. For each promise give a verdict: "delivered" (met in time), "delayed" (met but later than promised), "missed", "partly", or "unverifiable".
Return ONLY JSON: {{"verdicts":[{{"n":1,"verdict":"","evidence_type":"quote|table","evidence":"if quote: VERBATIM sentence from the LATER transcripts (max 30 words) that directly shows the outcome; if table: exact figures used e.g. 'Mar-26 EBITDA margin 60.7%'","note":"one short line"}}]}}
Rules: use only the filed numbers or the later transcripts. A quote must directly show the outcome, not merely mention the topic. Growth targets over several years are judged on the fiscal-year totals and growth percentages given. If the due date has not passed, or 'medium/long term' with no data yet, verdict is "unverifiable"."""
DEAD = set(); USED = {}
LADDER_X = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
LADDER_J = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
def gj(prompt, text, ladder):
    body = {"contents": [{"parts": [{"text": prompt + "\n\nTEXT:\n" + text[:300000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for m in ladder:
        if m in DEAD: continue
        for i in range(3):
            r = requests.post(f"{BASE}/models/{m}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=150)
            if r.status_code == 429:
                if "PerDay" in r.text: DEAD.add(m); p("  model out of daily quota:", m); break
                time.sleep(20 * (i + 1)); continue
            if r.status_code >= 500: time.sleep(15 * (i + 1)); continue
            if r.status_code != 200: p("  gemini http", m, r.status_code); DEAD.add(m); break
            try:
                t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                USED[m] = USED.get(m, 0) + 1
                return json.loads(re.sub(r"^```json|```$", "", t.strip())), m
            except Exception:
                return None, m
    return None, None
def grams(t):
    n = norm(t); return {" ".join(n[i:i + 4]) for i in range(len(n) - 3)}
def nums(s): return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (s or "").replace(",", ""))]
def table_text(rows):
    L = []; fy = {}
    for lab, m in rows:
        rev, eb, pat = m.get("revenue"), m.get("ebitda"), m.get("pat")
        em = round(100 * eb / rev, 1) if rev and eb is not None else None
        L.append(f"{lab}: revenue {rev}, monthly avg revenue {round(rev/3,1) if rev else None}, EBITDA {eb}, EBITDA margin {em}%, PAT {pat} ({m['basis']})")
        d = datetime.strptime("01-" + lab, "%d-%b-%y"); fy.setdefault(d.year + (1 if d.month > 3 else 0), []).append(m)
    prev = None
    for y, ms in sorted(fy.items()):
        if len(ms) == 4:
            rv = round(sum(x['revenue'] for x in ms), 1); g = f", revenue growth vs prior FY {round(100*(rv/prev-1),1)}%" if prev else ""
            pt = sum(x['pat'] for x in ms)
            L.append(f"FY{str(y)[2:]} total (Apr-Mar): revenue {rv}{g}, EBITDA {round(sum(x['ebitda'] for x in ms),1)}, PAT {round(pt,1)}, PAT margin {round(100*pt/rv,1)}%"); prev = rv
    return "\n".join(L)
H_ANN = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
def main():
    s = nse.sess()
    # 1 profile
    prof = store.load(SYM, "profile.json", {}) or {}
    prof.update({"symbol": SYM, "bse_code": CODE or prof.get("bse_code"), "name": NAME or prof.get("name"), "updated": NOW})
    store.save(SYM, "profile.json", prof)
    # 2 quarters
    rows = fd.merged(s, SYM)
    q = {lab: {k: v for k, v in m.items() if k != "rank"} for lab, m in rows}
    store.save(SYM, "quarters.json", {"unit": "Rs Cr", "note": "EBITDA = PBT + finance cost + depreciation - other income", "quarters": q})
    p("quarters:", len(q))
    # 3 governance / trust signals
    ann = []
    for a, z in (("01-01-2023", "31-12-2023"), ("01-01-2024", "31-12-2024"), ("01-01-2025", "31-12-2025"), ("01-01-2026", datetime.utcnow().strftime("%d-%m-%Y"))):
        try:
            j = s.get("https://www.nseindia.com/api/corporate-announcements", params={"index": "equities", "symbol": SYM, "from_date": a, "to_date": z}, headers=H_ANN, timeout=60).json()
        except Exception:
            j = []
        for x in j:
            ann.append({"date": (x.get("an_dt") or "")[:11], "desc": x.get("desc"), "text": (x.get("attchmntText") or "")[:300], "file": x.get("attchmntFile")})
    ann.sort(key=lambda r: (datetime.strptime(r["date"], "%d-%b-%Y") if r["date"] else datetime(1970, 1, 1), r["desc"] or ""))
    store.save(SYM, "filings.json", {"source": "NSE corporate-announcements", "count": len(ann), "items": ann})
    p("filings:", len(ann))
    try:
        h = s.get("https://www.nseindia.com/api/corporate-share-holdings-master", params={"index": "equities", "symbol": SYM}, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}, timeout=40).json()
        store.save(SYM, "holding.json", {"source": "NSE shareholding pattern", "rows": [{"date": x.get("date"), "promoter_pct": x.get("pr_and_prgrp"), "public_pct": x.get("public_val"), "revised": x.get("revisedStatus")} for x in h]})
        p("holding rows:", len(h))
    except Exception as e: p("holding err", repr(e)[:60])
    H2 = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"}
    try:
        sj = s.get("https://www.nseindia.com/api/corporate-sast-reg29", params={"index": "equities", "symbol": SYM}, headers=H2, timeout=40).json().get("data", [])
        pl = s.get("https://www.nseindia.com/api/corporate-pledgedata", params={"index": "equities", "symbol": SYM}, headers=H2, timeout=40).json()
        store.save(SYM, "sast.json", {"source": "NSE SAST Reg29 + pledge", "sast": [{k: x.get(k) for k in ("acquirerDate", "acqSaleType", "acquirerName", "noOfShareAcq", "noOfShareAft")} for x in sj], "pledge_records_returned": len(pl.get("data", [])) if isinstance(pl, dict) else None})
        p("sast rows:", len(sj))
    except Exception as e: p("sast err", repr(e)[:60])
    # 4 transcripts (cache raw text)
    tr = {}
    for x in ann:
        t = (x["text"] or "") + " " + (x["desc"] or ""); f = x["file"] or ""
        if "Analysts/Institutional" in (x["desc"] or "") and "transcript" in t.lower() and f.lower().endswith(".pdf") and "intimation" not in f.lower() and x["date"]:
            tr[f] = x["date"]
    tmeta = store.load(SYM, "transcripts.json", {"items": []}) or {"items": []}
    known = {i["url"]: i for i in tmeta["items"]}
    from pypdf import PdfReader
    for f, d in tr.items():
        key = hashlib.sha1(f.encode()).hexdigest()[:12]
        if f in known and store.load_raw(SYM, key): continue
        try:
            r = s.get(f, headers={"Referer": "https://www.nseindia.com/"}, timeout=90)
            txt = " ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:
            p(d, "download/parse failed", repr(e)[:50]); continue
        if len(txt) < 5000: p(d, "text too short (scanned?)"); continue
        store.save_raw(SYM, key, txt)
        known[f] = {"url": f, "filed": d, "key": key, "chars": len(txt)}
    items = sorted(known.values(), key=lambda i: datetime.strptime(i["filed"], "%d-%b-%Y"))
    # drop revised duplicates filed within 3 days with identical start
    ded = []
    for i in items:
        t = store.load_raw(SYM, i["key"]) or ""
        i["dup_of"] = None
        if ded and abs((datetime.strptime(i["filed"], "%d-%b-%Y") - datetime.strptime(ded[-1]["filed"], "%d-%b-%Y")).days) <= 3 and t[:300] == (store.load_raw(SYM, ded[-1]["key"]) or "")[:300]:
            i["dup_of"] = ded[-1]["url"]; continue
        ded.append(i)
    store.save(SYM, "transcripts.json", {"source": "NSE announcements (official transcripts)", "items": items})
    p("transcripts:", len(items), "unique:", len(ded))
    # 5 promises (cached)
    pdb = store.load(SYM, "promises.json", {"calls": {}}) or {"calls": {}}
    for i in ded:
        c = pdb["calls"].get(i["url"])
        if c and c.get("extractor") == EXTRACTOR: continue
        txt = store.load_raw(SYM, i["key"]); G = grams(txt)
        e, m = gj(QX, txt, LADDER_X)
        if isinstance(e, list): e = {"promises": e}
        if not e: p(i["filed"], "extract failed"); continue
        ok = [dict(x, id=f"{i['key']}-{k}", verdict=None) for k, x in enumerate(e.get("promises") or []) if isinstance(x, dict) and quote_ok(x.get("quote"), G)]
        pdb["calls"][i["url"]] = {"filed": i["filed"], "key": i["key"], "extractor": EXTRACTOR, "model": m, "extracted_on": NOW, "promises": ok}
        p(f"extracted {i['filed']}: {len(ok)} promises via {m}")
    store.save(SYM, "promises.json", pdb)
    # 6 judge (only when asked)
    if JUDGE:
        TT = table_text(rows); TTN = nums(TT)
        order = [i for i in ded]
        for n, i in enumerate(order):
            c = pdb["calls"].get(i["url"]); 
            if not c or not c["promises"]: continue
            later = order[n + 1:n + 3]
            if not later: continue
            todo = [x for x in c["promises"] if not x.get("verdict") or str(x["verdict"].get("label", "")).startswith("unverifiable") and x["verdict"].get("later_calls") != len(later)]
            if not todo: continue
            ltxt = [(l["filed"], store.load_raw(SYM, l["key"]) or "") for l in later]; LG = grams(" ".join(t for _, t in ltxt))
            plist = "\n".join(f"{k+1}. [{x.get('topic')}] {x.get('promise')} (due: {x.get('deadline')})" for k, x in enumerate(todo))
            v, m = gj(QJ.format(date=i["filed"], plist=plist, table=TT), "\n\n".join(f"--- LATER CALL filed {d} ---\n{t}" for d, t in ltxt), LADDER_J)
            if isinstance(v, list): v = {"verdicts": v}
            if not v: p(i["filed"], "judge failed"); continue
            got = {x.get("n"): x for x in (v.get("verdicts") or []) if isinstance(x, dict)}
            for k, x in enumerate(todo):
                jv = got.get(k + 1) or {}; label, et, ev = jv.get("verdict") or "unverifiable", jv.get("evidence_type"), jv.get("evidence") or ""
                ok = (et == "quote" and quote_ok(ev, LG)) or (et == "table" and nums(ev) and all(any(abs(a - b) <= 0.15 for b in TTN) for a in nums(ev)))
                if label != "unverifiable" and not ok: label = "unverifiable (evidence failed check)"
                x["verdict"] = {"label": label, "evidence_type": et, "evidence": ev, "note": jv.get("note"), "model": m, "judged_on": NOW, "later_calls": len(later)}
        store.save(SYM, "promises.json", pdb)
        tally = {}
        for c in pdb["calls"].values():
            for x in c["promises"]:
                l = (x.get("verdict") or {}).get("label", "not judged"); tally[l] = tally.get(l, 0) + 1
        p("TALLY", json.dumps(tally))
    p("gemini calls by model:", json.dumps(USED))
try:
    main()
except Exception:
    p("ERR", traceback.format_exc()[-900:])
publish()
