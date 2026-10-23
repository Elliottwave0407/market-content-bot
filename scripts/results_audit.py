"""Read-only coverage audit: BSE result filings of the last N days vs cards we posted (store/results). Per day: how many companies filed, how many got a card, how fast, and who got none (with the reason we can see)."""
import os, sys, json, glob, re
from datetime import datetime, timedelta
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl

N = int(os.environ.get("AUDIT_DAYS", "7"))
rpl.DAYS_BACK = N
posted = {}
for f in glob.glob("store/results/*.jsonl"):
    for ln in open(f, encoding="utf-8"):
        try: r = json.loads(ln)
        except Exception: continue
        m = re.match(r"BSE (\d+)\|([A-Za-z]{3}-\d\d)", str(r.get("key", "")))
        if m and r.get("ts"):
            c = m.group(1)
            if c not in posted or r["ts"] < posted[c]["ts"]: posted[c] = {"ts": r["ts"], "lat": r.get("latency_min"), "route": r.get("route")}
st = json.load(open("state/seen.json"))
pend_ids = set(st.get("pending", {}).keys())
SKIP = re.compile(r"intimation|newspaper|publication|clarification|schedule of|trading window|closure of", re.I)
with BSE(download_folder="/tmp") as b:
    rows = rpl.fetch_filings(b)
byday = defaultdict(dict)
for r in rows:
    txt = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
    if SKIP.search(txt) and not re.search(r"outcome|unaudited|audited|financial results", txt, re.I): continue
    code = str(r.get("SCRIP_CD")).strip(); day = (r.get("NEWS_DT") or "")[:10]
    cur = byday[day].get(code)
    if cur is None or r["NEWS_DT"] < cur["NEWS_DT"]: byday[day][code] = r
tot = defaultdict(int)
for day in sorted(byday):
    d = byday[day]; c = defaultdict(int); miss = []
    for code, r in d.items():
        pc = posted.get(code)
        filed = datetime.fromisoformat(r["NEWS_DT"][:19])
        if not pc: c["none"] += 1; miss.append((r["NEWS_DT"][11:16], code, (r.get("SLONGNAME") or "")[:24], "pending" if r["NEWSID"] in pend_ids else "-"))
        else:
            lag = (datetime.fromisoformat(pc["ts"]) - filed).total_seconds() / 60
            c["posted"] += 1
            c["<=15m" if lag <= 15 else "<=60m" if lag <= 60 else "same day >1h" if pc["ts"][:10] == day else "next day+"] += 1
    p(day, "filed", len(d), dict(c))
    for k, v in c.items(): tot[k] += v
    if miss and day >= (datetime.utcnow() + timedelta(hours=5, minutes=30) - timedelta(days=3)).strftime("%Y-%m-%d"):
        p("   no card:", "; ".join(f"{t} {cd} {nm} {pd}" for t, cd, nm, pd in sorted(miss)[:40]))
p("TOTAL", dict(tot))
publish()
