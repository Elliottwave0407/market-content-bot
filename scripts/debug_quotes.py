"""Read-only: for transcripts where few model quotes verify, show WHY (rejected quote vs the closest passage in the transcript). Prints short snippets of PUBLIC filings only."""
import os, sys, re, json, glob, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import concall_extract as CE
import concall_themes as CT

names = [x.strip().lower() for x in os.environ.get("ONLY", "CIE Automotive,Piramal Finance,LMW,Metro Brands").split(",") if x.strip()]
recs = {}
for f in glob.glob(os.path.join(CE.store.ROOT, "concall_facts_m20", "20*.jsonl")):
    for l in open(f):
        r = json.loads(l)
        if not r.get("skip") and any(n in r["name"].lower() for n in names):
            recs[r["key"]] = r
for k, r in list(recs.items())[:4]:
    txt = CE.prep(CT.pdf_text(r["src"]) or "")
    nt = CE.norm(txt); toks = nt.split()
    p("DOC", r["name"][:24], "words", len(toks), "n_raw", r["n_raw"], "n_ok", r["n_ok"])
    p("  text sample:", repr(txt[3000:3300]))
    for ch in CE.chunks(txt)[:1]:
        got = CE.call(CE.MODELS[0], ch) or {}
        shown = 0
        for it in got.get("items", []):
            q = str(it.get("quote") or "")
            nq = CE.norm(q)
            if nq and nq in nt:
                continue
            qt = nq.split()
            if len(qt) < 4 or shown >= 4:
                continue
            # best window: anchor on the first 3 words, else fall back to difflib on word windows
            best, bs = "", 0.0
            w = len(qt)
            step = max(1, w // 4)
            for i in range(0, max(1, len(toks) - w), step):
                win = toks[i:i + w]
                s = difflib.SequenceMatcher(None, qt, win).ratio()
                if s > bs:
                    bs, best = s, " ".join(win)
            shown += 1
            p(f"  REJECT sim={bs:.2f} model: {nq[:170]}")
            p(f"         closest: {best[:170]}")
publish()
