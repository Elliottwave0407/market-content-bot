"""Readiness screen: which companies have enough public data for a FinGod report card? No AI calls (free).
For each candidate it counts, from NSE: earnings-call transcripts filed in the last 3 years, quarterly financial filings, and shareholding history.
Candidates: env SYMBOLS (comma list) or, by default, BSE-listed companies in a market-cap band (Rs Cr) that have an NSE symbol.
Env: MCAP_MIN, MCAP_MAX (Rs Cr), TOP (how many candidates to check, largest by market cap within the band), OUT (json path).
Prints a ranked table and saves companydata/_readiness/screen.json."""
import os, sys, re, json, time, tempfile
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H_ANN = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
H_INT = {"Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing"}
MIN = float(os.environ.get("MCAP_MIN", "2000")); MAX = float(os.environ.get("MCAP_MAX", "60000")); TOP = int(os.environ.get("TOP", "120"))
syms = [x.strip().upper() for x in os.environ.get("SYMBOLS", "").split(",") if x.strip()]
mc_of = {}
if not syms:
    from bse import BSE
    code2sym = json.load(open(os.path.join(ROOT, "state", "symbols.json")))["m"]
    cap = {}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS"):
            try:
                for x in b.listSecurities(group=g):
                    try: v = float(str(x.get("Mktcap") or "0").replace(",", ""))
                    except Exception: v = 0
                    cap[str(x.get("SCRIP_CD")).strip()] = v
            except Exception: continue
    rows = sorted(((v, code2sym[c]) for c, v in cap.items() if c in code2sym and MIN <= v <= MAX), reverse=True)[:TOP]
    syms = [s for _, s in rows]; mc_of = {s: v for v, s in rows}
    p(f"candidates: {len(syms)} (market cap Rs {MIN:,.0f}-{MAX:,.0f} Cr, top {TOP} by size)")
today = datetime.utcnow(); res = []
def get(s, url, params, hdr):
    for k in range(3):
        try:
            r = s.get(url, params=params, headers=hdr, timeout=45)
            if r.status_code == 200: return r.json()
        except Exception: pass
        time.sleep(2 * (k + 1))
        s = nse.sess()
    return None
t0 = time.time()
for i, sym in enumerate(syms):
    s = nse.sess(); n_tr, dates, n_ann = 0, [], 0
    for y in (today.year - 3, today.year - 2, today.year - 1, today.year):
        a = f"01-01-{y}"; z = f"31-12-{y}" if y < today.year else today.strftime("%d-%m-%Y")
        j = get(s, "https://www.nseindia.com/api/corporate-announcements", {"index": "equities", "symbol": sym, "from_date": a, "to_date": z}, H_ANN) or []
        for x in j:
            n_ann += 1
            t = ((x.get("attchmntText") or "") + " " + (x.get("desc") or "")).lower(); f = (x.get("attchmntFile") or "").lower()
            if "analysts/institutional" in (x.get("desc") or "").lower() and "transcript" in t and f.endswith(".pdf") and "intimation" not in f:
                dates.append((x.get("an_dt") or "")[:11])
    d = get(s, "https://www.nseindia.com/api/integrated-filing-results", {"index": "equities", "symbol": sym}, H_INT) or {}
    fin = [x for x in (d.get("data") or []) if "Financial" in (x.get("type") or "")]
    qe = {x.get("qe_Date") for x in fin if x.get("qe_Date")}
    h = get(s, "https://www.nseindia.com/api/corporate-share-holdings-master", {"index": "equities", "symbol": sym}, {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}) or []
    tr_unique = sorted({x for x in dates if x})
    last_tr = None
    try: last_tr = max(datetime.strptime(x, "%d-%b-%Y") for x in tr_unique) if tr_unique else None
    except Exception: pass
    fresh = bool(last_tr and (today - last_tr).days <= 120)
    score = min(len(tr_unique), 12) * 5 + min(len(qe), 12) * 2 + (10 if fresh else 0) + (4 if len(h) >= 8 else 0)    # max 98
    res.append({"symbol": sym, "mcap_cr": round(mc_of.get(sym, 0)), "transcripts_3y": len(tr_unique), "quarters_filed": len(qe), "holding_rows": len(h), "last_transcript": last_tr.strftime("%d-%b-%Y") if last_tr else None, "fresh": fresh, "readiness": score})
    if (i + 1) % 10 == 0: p(f"  {i+1}/{len(syms)} checked, {time.time()-t0:.0f}s")
res.sort(key=lambda r: (-r["readiness"], -r["mcap_cr"]))
os.makedirs(os.path.join(ROOT, "companydata", "_readiness"), exist_ok=True)
json.dump({"asof": today.strftime("%Y-%m-%d"), "band_cr": [MIN, MAX], "rows": res}, open(os.path.join(ROOT, "companydata", "_readiness", "screen.json"), "w"), indent=1)
p("symbol | mcap Cr | transcripts 3y | quarters | last call | score")
for r in res[:40]: p(f"{r['symbol']:<12}{r['mcap_cr']:>8,} {r['transcripts_3y']:>4} {r['quarters_filed']:>4}  {r['last_transcript'] or '-':<12}{r['readiness']:>4}")
ok = sum(1 for r in res if r["transcripts_3y"] >= 8 and r["quarters_filed"] >= 8)
p(f"ready (>=8 transcripts and >=8 quarters): {ok} of {len(res)}")
publish()
