"""Price-reaction monotonicity check for Verdict v3 (calibration only, not a prediction claim)."""
import sys, os, gzip, glob, json, collections, statistics as st, datetime as dt, bisect
sys.path.insert(0, os.path.dirname(__file__))
import verdict_v3 as v, verdict_v3_proto as p
R = os.path.join(os.path.dirname(__file__), "..", "store") + "/"
px = collections.defaultdict(dict)       # isin -> {date: close}
dates = []
for f in sorted(glob.glob(R + "prices/d/2026-*_N.csv.gz")):
    d = os.path.basename(f)[:10]; dates.append(d)
    for l in gzip.open(f, "rt"):
        a = l.split(",")
        if len(a) > 8 and a[4] == "EQ":
            try: px[a[2]][d] = float(a[8])
            except: pass
dates = sorted(set(dates))
filed = {}
for l in open(R + "results_if/numbers.jsonl"):
    r = json.loads(l)
    if r.get("isin") and r.get("filed") and r["to"] == "30-JUN-2026":
        try: filed.setdefault(r["isin"], dt.datetime.strptime(r["filed"][:11], "%d-%b-%Y").strftime("%Y-%m-%d"))
        except: pass
_, F = p.build(2026 * 4 + 1)
ev = []
for i, f in F.items():
    t = v.rate(f)[0]; d = filed.get(i)
    if t not in v.TIERS or not d or i not in px: continue
    k = bisect.bisect_left(dates, d)          # first trading day on/after filing
    if k < 1 or k + 2 >= len(dates): continue
    b, e = px[i].get(dates[k - 1]), px[i].get(dates[k + 2])
    if b and e: ev.append((t, (e / b - 1) * 100))
mkt = st.median(r for _, r in ev)
by = collections.defaultdict(list)
for t, r in ev: by[t].append(r - mkt)
print("events", len(ev), "market median %+.2f" % mkt)
for t in v.TIERS: print("%-12s n=%4d  median excess return %+.2f pct  mean %+.2f" % (t, len(by[t]), st.median(by[t]), st.mean(by[t])))
