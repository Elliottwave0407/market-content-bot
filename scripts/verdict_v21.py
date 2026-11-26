"""Quarterly Verdict v2.1 (26 Nov 2026). NOT YET WIRED INTO CARDS. v2.0 (scripts/quarter_rating.py rate6, v2=True) stays the live rating until a numbered release.
v2.1 = v2.0 plus two rules, both tested on Mar-26 and Jun-26 price reactions (scripts/verdict_v21_test.py):
  R1  a Blockbuster needs the margin not falling: margin down more than 1 pt QoQ, or any fall YoY, caps it at Excellent (such results reacted +3.0% against +6.5%).
  R1b a Blockbuster needs profit up at least 25% YoY (a turnaround from a loss base is not measured and is left to the existing Excellent cap).
  R2  flat momentum: when sales, EBITDA and profit are all up less than 15% QoQ (seasonally adjusted), an Excellent or Blockbuster steps down one tier, never below Strong (flat-QoQ top tiers reacted +1% to +2%, moving ones +5% to +6%).
plus two TAGS (they never change the tier):
  Versus expectation: acceleration of the YoY growth and margin change against the company's own previous quarter. Ahead / In line / Behind.
  Momentum: sales, EBITDA, profit QoQ (seasonally adjusted). Building / Mixed / Flat / Fading.
usage: rate21(cur, prev, yago, yprev=None, older=None) with the same dicts as rate6 (revenue, ebitda, pat, basis; Rs any unit)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import quarter_rating as qr

RATING_VERSION = "v2.1"
ASC = ["Poor", "Weak", "Steady", "Strong", "Excellent", "Blockbuster"]
FLAT_X = 15           # percent QoQ
AHEAD, BEHIND = 25.0, -10.0

def _g(a, b):
    return None if a is None or b in (None, 0) or b <= 0 else (a / b - 1) * 100

def tags(cur, prev, yago, yprev, m):
    """Versus-expectation and momentum tags. m = rate6's metrics dict."""
    out = {"vs_expectation": None, "momentum": None, "acceleration": None}
    v = [m.get("rev_qoq"), m.get("ebitda_qoq"), m.get("pat_qoq")]
    if all(a is not None for a in v):
        out["momentum"] = "Building" if all(a >= 10 for a in v) else "Fading" if all(a < 0 for a in v) else "Flat" if all(a < FLAT_X for a in v) else "Mixed"
    if yprev and yprev.get("revenue") not in (None, 0) and yprev.get("ebitda") is not None:
        mg = lambda q: q["ebitda"] / q["revenue"] * 100
        now = [x for x in (_g(cur["revenue"], yago["revenue"]), _g(cur["ebitda"], yago["ebitda"])) if x is not None]
        then = [x for x in (_g(prev["revenue"], yprev["revenue"]), _g(prev["ebitda"], yprev["ebitda"])) if x is not None]
        if len(now) == 2 and len(then) == 2:
            s = 0.7 * (sum(now) / 2 - sum(then) / 2) + 0.3 * ((mg(cur) - mg(yago)) - (mg(prev) - mg(yprev))) * 5
            out["acceleration"] = round(s, 1)
            out["vs_expectation"] = "Ahead" if s >= AHEAD else "Behind" if s <= BEHIND else "In line"
    return out

def rate21(cur, prev, yago, yprev=None, older=None, **kw):
    r = qr.rate6(cur, prev, yago, yprev, v11=True, v12=True, v2=True, older=older, **kw)
    if r.get("tier") is None: return r
    r["v2_tier"] = r["tier"]
    k = ASC.index(r["tier"]); m = r["m"]; notes = []
    if k == 5 and (m["margin_qoq_pts"] < -1 or m["margin_yoy_pts"] < 0):
        k = 4; notes.append("margin not holding (Blockbuster needs margin flat or up)")
    if k == 5 and m.get("pat_yoy") is not None and m["pat_yoy"] < 25:
        k = 4; notes.append("profit growth under 25% (Blockbuster needs profit up at least 25%)")
    if k >= 4 and all(m.get(x) is not None for x in ("rev_qoq", "ebitda_qoq", "pat_qoq")) and all(m[x] < FLAT_X for x in ("rev_qoq", "ebitda_qoq", "pat_qoq")):
        k = max(3, k - 1); notes.append("sequential momentum is flat")
    r["tier"] = ASC[k]; r["v21_notes"] = notes; r["tags"] = tags(cur, prev, yago, yprev, m); r["version"] = RATING_VERSION
    return r
