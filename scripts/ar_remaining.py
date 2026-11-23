"""Prints how many FY2026 annual reports still need reading (no facts file yet, or an old-style skip)."""
import json, os
R = os.path.join(os.path.dirname(__file__), "..", "store") + "/"; FY = 2026; n = 0
for l in open(R + "annual_reports/merged.jsonl"):
    r = json.loads(l)
    if r["fy"] != FY or not r.get("isin") or not r.get("url"): continue
    fn = R + "annual_report_facts/%s_%d.json" % (r["isin"], FY)
    if not os.path.exists(fn): n += 1; continue
    try: d = json.load(open(fn))
    except Exception: n += 1; continue
    if d.get("skip") and d.get("v") != 2: n += 1
print(n)
