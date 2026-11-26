"""Replay of v2.1 against v2.0 on Mar-26 and Jun-26 results (calibration + sanity). usage: python3 scripts/verdict_v21_replay.py"""
import sys, os, collections, statistics as st
sys.path.insert(0, os.path.dirname(__file__))
import verdict_method_bakeoff as b, verdict_v3_proto as p, verdict_v21 as v
ASC = v.ASC
for q, lab in ((2026 * 4, "Mar-26"), (2026 * 4 + 1, "Jun-26")):
    n = ch = 0; moves = collections.Counter(); notes = collections.Counter(); tg = collections.Counter(); mix2 = collections.Counter(); mix21 = collections.Counter(); keys = []
    for (i, qq) in list(p.D):
        if qq != q: continue
        c, y, pv = p.D.get((i, q)), p.D.get((i, q - 4)), p.D.get((i, q - 1))
        if not (c and y and pv): continue
        yp = p.D.get((i, q - 5))
        try: r = v.rate21(b.mk(c), b.mk(pv), b.mk(y), b.mk(yp) if yp else None)
        except Exception: continue
        if r.get("tier") is None: continue
        n += 1; mix2[r["v2_tier"]] += 1; mix21[r["tier"]] += 1
        if r["tier"] != r["v2_tier"]: ch += 1; moves[(r["v2_tier"], r["tier"])] += 1
        for x in r["v21_notes"]: notes[x] += 1
        tg[(r["tags"]["vs_expectation"], r["tags"]["momentum"])] += 1
        keys.append(r)
    print("\n==== %s: %d rated; tier changed v2 -> v2.1 for %d (%.1f%%) ====" % (lab, n, ch, ch / n * 100))
    print("mix v2  :", {t: round(mix2[t] / n * 100, 1) for t in ASC[::-1]})
    print("mix v2.1:", {t: round(mix21[t] / n * 100, 1) for t in ASC[::-1]})
    print("moves:", dict(moves)); print("reasons:", dict(notes))
    ve = collections.Counter(k["tags"]["vs_expectation"] for k in keys); mo = collections.Counter(k["tags"]["momentum"] for k in keys)
    print("tags versus expectation:", dict(ve), "| momentum:", dict(mo))
    bad = sum(1 for k in keys if k["tier"] == "Blockbuster" and (k["m"]["margin_yoy_pts"] < 0 or k["m"]["margin_qoq_pts"] < -1 or (k["m"]["pat_yoy"] if k["m"]["pat_yoy"] is not None else 99) < 25))
    bad2 = sum(1 for k in keys if k["v2_tier"] == "Blockbuster" and (k["m"]["margin_yoy_pts"] < 0 or k["m"]["margin_qoq_pts"] < -1 or (k["m"]["pat_yoy"] if k["m"]["pat_yoy"] is not None else 99) < 25))
    print("Blockbuster never-event breaches (falling margin or profit growth under 25%%): v2 %d -> v2.1 %d" % (bad2, bad))
