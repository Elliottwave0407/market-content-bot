"""Sector map for every company that has concall transcripts. Free sources only:
 1. NSE official index constituent CSVs (Nifty Total Market ~755 + microcap/smallcap lists): macro-sector 'Industry', joined by ISIN.
 2. BSE security lists (all groups): BSE code -> ISIN and symbol.
 3. Yahoo Finance via yfinance (sector + industry) for companies NSE's lists do not cover; cached so reruns only fetch what is missing.
Output: store/sector_map/sector_map.json  {code: {name, isin, symbol, nse_sector, yf_sector, yf_industry, src}}  + summary.json. Never touches the concall facts."""
import os, sys, io, csv, json, time, glob, tempfile, traceback, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
ROOT = "store/sector_map"; os.makedirs(ROOT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
BUDGET = float(os.environ.get("BUDGET_MIN", "40")) * 60; T0 = time.time()
try:
    codes = {}
    for f in glob.glob("store/concall_themes/*.jsonl"):
        for l in open(f, encoding="utf-8"):
            try: d = json.loads(l)
            except Exception: continue
            if d.get("code"): codes.setdefault(str(d["code"]), d.get("name") or "")
    p("companies with concall transcripts:", len(codes))
    nse = {}
    for n in ("ind_niftytotalmarket_list", "ind_nifty500list", "ind_niftymicrocap250_list", "ind_niftysmallcap250list"):
        try:
            r = requests.get(f"https://nsearchives.nseindia.com/content/indices/{n}.csv", headers=UA, timeout=40)
            for x in csv.DictReader(io.StringIO(r.text)): nse.setdefault(x["ISIN Code"], (x["Industry"], x["Symbol"]))
        except Exception as e: p("NSE csv error", n, repr(e)[:60])
    p("NSE ISINs with sector:", len(nse))
    bse = {}
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "X", "XT", "T", "Z", "M", "MT", "MS", "P", "R", "F", "IF", "XD", "ZP", "SS", "ST", "Y"):
            try:
                rows = b.listSecurities(group=g)
                for r in rows: bse[str(r["SCRIP_CD"]).strip()] = (r.get("ISIN_NUMBER"), r.get("scrip_id"), r.get("Scrip_Name"))
                p("BSE group", g, len(rows))
            except Exception as e: p("BSE group", g, "none", type(e).__name__)
    p("BSE codes known:", len(bse))
    try: cache = json.load(open(f"{ROOT}/yahoo_cache.json"))
    except Exception: cache = {}
    out = {}
    need = []
    for c, nm in codes.items():
        isin, sym, bn = bse.get(c, (None, None, None))
        e = {"name": nm or bn, "isin": isin, "symbol": sym}
        if isin in nse: e["nse_sector"] = nse[isin][0]; e["nse_symbol"] = nse[isin][1]; e["src"] = "nse"
        out[c] = e
        if "nse_sector" not in e: need.append(c)
    p("covered by NSE lists:", len(codes) - len(need), "| need Yahoo:", len(need))
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yfinance"], check=True)
    import yfinance as yf
    fetched = 0
    for c in need:
        e = out[c]
        if c in cache: v = cache[c]
        else:
            if time.time() - T0 > BUDGET: break
            v = {}
            tries = ([f"{e['symbol']}.NS"] if e.get("symbol") else []) + [f"{c}.BO"] + ([f"{e['symbol']}.BO"] if e.get("symbol") else [])
            for t in tries:
                try:
                    i = yf.Ticker(t).get_info()
                    if i.get("sector") or i.get("industry"): v = {"sector": i.get("sector"), "industry": i.get("industry"), "t": t}; break
                except Exception: pass
                time.sleep(0.4)
            cache[c] = v; fetched += 1
            if fetched % 40 == 0: json.dump(cache, open(f"{ROOT}/yahoo_cache.json", "w"))
            time.sleep(0.4)
        if v.get("sector") or v.get("industry"): e["yf_sector"] = v.get("sector"); e["yf_industry"] = v.get("industry"); e["src"] = "yahoo"
    json.dump(cache, open(f"{ROOT}/yahoo_cache.json", "w"))
    for c, e in out.items(): e.setdefault("src", "none")
    json.dump(out, open(f"{ROOT}/sector_map.json", "w"), separators=(",", ":"))
    import collections
    cnt = collections.Counter(e["src"] for e in out.values())
    summ = {"companies": len(out), "by_source": dict(cnt), "yahoo_fetched_this_run": fetched, "yahoo_cached": len(cache)}
    json.dump(summ, open(f"{ROOT}/summary.json", "w"), indent=1)
    p("RESULT", json.dumps(summ))
    p("sample none:", [(c, e["name"]) for c, e in out.items() if e["src"] == "none"][:15])
except Exception:
    p("ERROR", traceback.format_exc()[-800:])
publish()
