"""List BSE-listed companies (with an NSE symbol) by market-cap band and save a stratified random sample -> companydata/_readiness/universe_<name>.json.
Env: BANDS 'name:min:max,name:min:max' (Rs Cr), N per band (default 70), SEED."""
import os, sys, json, tempfile, random
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bands = [b.split(":") for b in os.environ.get("BANDS", "small:500:5000,micro:100:500").split(",")]
N, rnd = int(os.environ.get("N", "70")), random.Random(int(os.environ.get("SEED", "7")))
code2sym = json.load(open(os.path.join(ROOT, "state", "symbols.json")))["m"]
cap = {}
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS"):
        try:
            for x in b.listSecurities(group=g):
                try: v = float(str(x.get("Mktcap") or "0").replace(",", ""))
                except Exception: v = 0
                cap[str(x.get("SCRIP_CD")).strip()] = (v, g)
        except Exception as e: p("group", g, "failed", repr(e)[:50])
out = {}
for name, lo, hi in bands:
    pool = sorted((c, v, g) for c, (v, g) in cap.items() if c in code2sym and float(lo) <= v <= float(hi))
    pick = rnd.sample(pool, min(N, len(pool)))
    out[name] = [{"symbol": code2sym[c], "mcap_cr": round(v), "group": g} for c, v, g in pick]
    p(name, f"Rs {lo}-{hi} Cr: pool {len(pool)}, sampled {len(pick)}; groups {dict((g, sum(1 for _, _, gg in pick if gg == g)) for g in set(g for _, _, g in pick))}")
os.makedirs(os.path.join(ROOT, "companydata", "_readiness"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "companydata", "_readiness", "universe_smallcap.json"), "w"), indent=1)
publish()
