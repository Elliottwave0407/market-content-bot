"""Fetch the text of governance-relevant filings (orders, deviations, clarifications, ratings, KMP exits) for a company. No LLM."""
import os, sys, io, json, hashlib, traceback
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, store
SYM = os.environ.get("SYMBOL", "E2E").strip().upper()
WANT = ("Action(s) initiated or orders passed", "Statement of deviation(s) or variation(s) under Reg. 32", "Reply to Clarification- Financial results", "Credit Rating",
        "Resignation of Director/KMP/SMP", "Annual Secretarial Compliance Report", "Cessation", "Resignation", "Related Party Transactions", "News Verification")
try:
    from pypdf import PdfReader
    s = nse.sess(); f = store.load(SYM, "filings.json", {"items": []})["items"]
    docs = store.load(SYM, "trust_docs.json", {"items": []}); have = {d["file"] for d in docs["items"]}
    for x in f:
        if x["desc"] not in WANT or not x.get("file") or not str(x["file"]).lower().endswith(".pdf") or x["file"] in have: continue
        try:
            r = s.get(x["file"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60)
            t = " ".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:
            t = "FETCH_ERROR " + repr(e)[:60]
        docs["items"].append({"date": x["date"], "desc": x["desc"], "file": x["file"], "text": " ".join(t.split())[:3500]})
    docs["items"].sort(key=lambda d: __import__("datetime").datetime.strptime(d["date"], "%d-%b-%Y"))
    store.save(SYM, "trust_docs.json", docs)
    p("docs stored:", len(docs["items"]))
    for d in docs["items"]:
        if d["desc"].startswith(("Action", "Statement of dev", "Reply to Clar", "Credit")):
            p(f"-- {d['date']} {d['desc'][:30]}: {d['text'][:700]}")
except Exception:
    p("ERR", traceback.format_exc()[-700:])
publish()
