"""Recompute code scores (quant + pillars) and print one combined summary. No API calls."""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import store, score_quant, score_pillars
SYM = os.environ.get("SYMBOL", "E2E").strip().upper()
try:
    a = score_quant.main(SYM); b = score_pillars.main(SYM); P = store.load(SYM, "pillars.json") or {}
    tot = 0.0; mx = 0.0; rows = []
    for k, v in a["points"].items():
        if v["score"] is None: rows.append((k, "n/a", v["max"])); continue
        tot += v["score"]; mx += v["max"]; rows.append((k, v["score"], v["max"]))
    for k, v in b["points"].items():
        tot += v["score"]; mx += max(v["max"], 0); rows.append((k, v["score"], v["max"]))
    for k, s, m in rows: p(f"{k:24} {str(s):>5} / {m}")
    nq = P.get("n_extracted") or 0; nk = len(P.get("facts") or [])
    p(f"TOTAL {tot:.1f} of {mx:.0f} (risk penalty included)  | pillar facts: {nk} audit-confirmed of {nq} quote-verified")
    for k, v in b["points"].items(): p(" *", k, v["score"], "|", v["note"][:260])
    p("TRUST GATE:", a["trust_gate"]["status"])
    wt = a["points"].get("walk_the_talk"); p("WALK THE TALK:", wt and (wt["score"], wt["note"][:200]))
    a["provisional_total"] = round(tot, 1); a["provisional_max"] = round(mx); store.save(SYM, "score.json", a)
except Exception:
    p("ERR", traceback.format_exc()[-900:])
publish()
