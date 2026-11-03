"""DRY RUN: render PREVIEW result cards for 'numbers not shown' stubs using NSE structured numbers. Nothing is posted anywhere.
Reads store/stub_dry/result.json (from nse_backup_dry.py). Writes PNGs to out/nse_preview/ (uploaded as a workflow artifact).
Env: N (how many stubs, default 12), SYMS (optional comma list of NSE symbols to force)."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))
import fin_data as fd
import nse_results as nr
import card
from ci_out import p, publish

N = int(os.environ.get("N", "12"))
QEND = ["30-sep-2026", "30-jun-2026", "31-mar-2026", "31-dec-2025", "30-sep-2025"]
LAB = ["Sep-26", "Jun-26", "Mar-26", "Dec-25", "Sep-25"]
MILLION = ("revenue", "ebitda", "pbt", "pat", "fin", "oth")      # BSE-style cards hold Rs million; NSE parse is Rs Cr
res = json.load(open("store/stub_dry/result.json"))["rows"]
names = {}
try:
    for k, v in json.load(open("state/seen.json")).get("names", {}).items(): names[k] = v
except Exception: pass
cand = [r for r in res if r["kind"] == "stub" and r["status"] == "ok" and not r.get("half")]
force = [x for x in os.environ.get("SYMS", "").split(",") if x]
if force: cand = [r for r in res if r.get("sym") in force]
cand = cand[:N]
os.makedirs("out/nse_preview", exist_ok=True)
done = 0
for r in cand:
    sym, basis, idx = r["sym"], r["basis"], r.get("index", "equities")
    s = nr.sess()
    try:
        d = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=40).json().get("data", [])
    except Exception as e:
        p(sym, "list failed", repr(e)[:50]); continue
    quarters = []
    for qe, lab in zip(QEND, LAB):
        best = None
        for x in d:
            if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"): continue
            if not str(x.get("qe_Date") or "").lower().startswith(qe): continue
            b = "consolidated" if x.get("consolidated") == "Consolidated" else "standalone"
            if b != basis: continue
            if best is None or (x.get("creation_Date") or "") >= (best.get("creation_Date") or ""): best = x
        m = None
        if best:
            try:
                m = fd.parse_xbrl(nr.sess().get(best["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text)
            except Exception: m = None
        if m: m = {k: (round(v * 10, 2) if k in MILLION and isinstance(v, (int, float)) else v) for k, v in m.items()}
        quarters.append({"q": lab, "m": m or {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}})
        time.sleep(0.4)
    have = [bool(q["m"].get("revenue") is not None) for q in quarters]
    p(sym, basis, "quarters found:", have)
    if not have[0]: continue
    out = f"out/nse_preview/{r['code']}_{sym}_{basis}.png"
    try:
        card.render(names.get(r["code"], sym), f"BSE {r['code']}", basis, quarters, out)
        done += 1
    except Exception as e:
        p(sym, "render failed", repr(e)[:80])
p("previews rendered", done, "of", len(cand))
publish()
