"""Read-only: today's BSE 'Result' rows + early rows vs what the live engine has posted/skipped (state + store). Public company names/codes only, no group ids."""
import os, sys, json, glob
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl

IST = datetime.utcnow() + timedelta(hours=5, minutes=30)
today = IST.strftime("%Y-%m-%d")
posted_keys = set()
for f in glob.glob("store/results/*.jsonl"):
    for ln in open(f, encoding="utf-8"):
        try:
            r = json.loads(ln)
            if str(r.get("ts", ""))[:7] == today[:7]: posted_keys.add(str(r.get("key", "")).split("|")[0])
        except Exception: pass
try:
    st = json.load(open("state/seen.json"))
except Exception:
    st = {}
p("state keys:", list(st.keys())[:8], "posted ids in state:", len(st.get("posted", [])) if isinstance(st, dict) else "?")
seen_ids = set(st.get("posted", [])) if isinstance(st, dict) else set()
with BSE(download_folder="/tmp") as b:
    rows = rpl.fetch_filings(b)
rows = [r for r in rows if (r.get("NEWS_DT") or "")[:10] == today]
p("today IST", today, "| BSE result/early rows today:", len(rows))
miss = 0
for r in rows:
    code = str(r.get("SCRIP_CD")).strip()
    nm = (r.get("SLONGNAME") or "")[:30]
    hit = ("BSE " + code) in posted_keys
    mark = "posted" if hit else ("id-marked" if r.get("NEWSID") in seen_ids else "NOT POSTED")
    if mark != "posted": miss += 1
    p((r.get("NEWS_DT") or "")[11:16], code, nm, "|", r.get("CATEGORYNAME"), "|", ("early" if r.get("_EARLY") else "result"), "|", mark, "|", (r.get("HEADLINE") or "")[:70])
p("not posted:", miss)
publish()
