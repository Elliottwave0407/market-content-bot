"""Annual report listing (BSE) from FROM (default 2024-04-01) in 7-day windows: category Others / subcategory 'Reg. 34 (1) Annual Report' (how BSE labels them; also keeps AGM/EGM filings whose headline mentions the annual report is NOT done here).
Resumable. Cache store/annual_reports/bse_ar.jsonl, state _bse_windows_done.json. Env FROM, BUDGET_MIN, WORKERS(3), LIMIT_WINDOWS (test)."""
import os, sys, json, time, tempfile
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
from ci_out import p, publish
import store
from bse import BSE
OUT = os.path.join(store.ROOT, "annual_reports"); os.makedirs(OUT, exist_ok=True)
CACHE = os.path.join(OUT, "bse_ar.jsonl"); STATE = os.path.join(OUT, "_bse_windows_done.json")
FROM = os.environ.get("FROM") or "2024-04-01"; BUDGET = float(os.environ.get("BUDGET_MIN") or "120"); W = int(os.environ.get("WORKERS") or "3"); LW = int(os.environ.get("LIMIT_WINDOWS") or "0"); T0 = time.time()
try: done = set(json.load(open(STATE)))
except Exception: done = set()
rows = {}
if os.path.exists(CACHE):
    for l in open(CACHE, encoding="utf-8"):
        try: r = json.loads(l); rows[r["id"]] = r
        except Exception: pass
# the last 21 days are always re-checked (late filings, AGM season)
cut = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d")
done = {k for k in done if k < cut}
d = datetime.fromisoformat(FROM); wins = []
while d <= datetime.now():
    e = min(d + timedelta(days=6), datetime.now()); k = d.strftime("%Y-%m-%d")
    if k not in done: wins.append((k, d, e))
    d = e + timedelta(days=1)
if LW: wins = wins[-LW:]
p("windows todo", len(wins), "already", len(done), "cached rows", len(rows))
def fetch(w):
    k, a, b = w; err = None
    for attempt in range(4):
        try:
            out = []; pg = 1
            with BSE(download_folder=tempfile.mkdtemp()) as bse:
                while pg <= 120:
                    r = bse.announcements(page_no=pg, from_date=a, to_date=b, category="Others", subcategory="Reg. 34 (1) Annual Report")
                    t = r.get("Table", [])
                    if not t: break
                    out += t
                    if len(out) >= (r.get("Table1") or [{}])[0].get("ROWCNT", 0): break
                    pg += 1
            return k, out, None
        except Exception as ex:
            err = type(ex).__name__; time.sleep(4 * (attempt + 1))
    return k, None, err
nw = errs = 0; subs = {}
with ThreadPoolExecutor(W) as ex:
    for i in range(0, len(wins), W * 4):
        if (time.time() - T0) / 60 > BUDGET: break
        for k, out, err in ex.map(fetch, wins[i:i + W * 4]):
            if out is None: errs += 1; continue
            for x in out:
                subs[(x.get("CATEGORYNAME"), x.get("SUBCATNAME"))] = subs.get((x.get("CATEGORYNAME"), x.get("SUBCATNAME")), 0) + 1
                if not x.get("ATTACHMENTNAME"): continue
                rid = x.get("NEWSID") or (str(x.get("SCRIP_CD")) + x.get("ATTACHMENTNAME"))
                rows[rid] = {"id": rid, "code": str(x.get("SCRIP_CD")).strip(), "name": x.get("SLONGNAME"), "dt": (x.get("NEWS_DT") or "")[:19], "head": (x.get("HEADLINE") or "")[:200], "att": x.get("ATTACHMENTNAME"), "url": f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{x.get('ATTACHMENTNAME')}"}
            done.add(k); nw += 1
        json.dump(sorted(done), open(STATE, "w")); open(CACHE, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()))
        p("progress windows", nw, "rows", len(rows), "errors", errs, f"{(time.time()-T0)/60:.0f} min")
json.dump(sorted(done), open(STATE, "w")); open(CACHE, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()))
p("categories seen:", dict(list(subs.items())[:6]))
p("end: windows done", len(done), "| BSE annual report filings", len(rows), "| errors", errs, "| companies", len({r["code"] for r in rows.values()}))
publish()
