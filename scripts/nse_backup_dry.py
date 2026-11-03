"""DRY RUN ONLY (never posts anything): how many 'numbers not shown' cards could be replaced by NSE's own structured (XBRL) numbers,
and does the NSE XBRL parser agree with BSE where both exist. Result goes to store/stub_dry/result.json; the log carries counts only.
Env: QE (default 30-Sep-2026), VALID_N (validation sample size, default 40), LIMIT (0 = all stubs)."""
import os, sys, json, time, random, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import requests
import fin_data as fd
import nse_results as nr
import results_fetcher as rf
from ci_out import p, publish

QE = os.environ.get("QE", "30-Sep-2026").lower()
VALID_N = int(os.environ.get("VALID_N", "40"))
LIMIT = int(os.environ.get("LIMIT", "0"))
LABEL = "Sep-26"
seen = json.load(open("state/seen.json"))
symmap = json.load(open("state/symbols.json")).get("m", {})
stubs = sorted({k.split("|")[0] for k in seen["posted"] if k.endswith("|" + LABEL + "|na")})
valid = {}
for k in seen["posted"]:
    a = k.split("|")
    if len(a) == 3 and a[1] == LABEL and a[2] in ("consolidated", "standalone"):
        valid.setdefault(a[0], a[2])
random.seed(7)
vcodes = random.sample(sorted(c for c in valid if c in symmap and c not in stubs), min(VALID_N, len(valid)))
if LIMIT: stubs = stubs[:LIMIT]; vcodes = vcodes[:LIMIT]
p("stub filings", len(stubs), "validation sample", len(vcodes))

def nse_rows(sym):
    s = nr.sess()
    for idx in ("equities", "sme"):
        for t in range(2):
            try:
                r = s.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=40)
                if r.status_code == 200 and r.text.strip():
                    d = r.json().get("data", [])
                    if d: return idx, d
                    break
                nr._S["sess"] = None; s = nr.sess()
            except Exception:
                nr._S["sess"] = None; time.sleep(2); s = nr.sess()
        time.sleep(0.5)
    return None, []

def nse_quarter(sym):
    idx, d = nse_rows(sym)
    if not d: return {"status": "no_nse_record"}
    best = None
    for x in d:
        if "Financial" not in (x.get("type") or "") or x.get("xbrl") in (None, "None"): continue
        if not str(x.get("qe_Date") or "").lower().startswith(QE): continue
        basis = "consolidated" if x.get("consolidated") == "Consolidated" else "standalone"
        rank = (1 if basis == "consolidated" else 0, x.get("creation_Date") or "")
        if best is None or rank >= best[0]: best = (rank, x, basis)
    if best is None: return {"status": "quarter_not_on_nse", "index": idx}
    _, x, basis = best
    try:
        t = nr.sess().get(x["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=60).text
        m = fd.parse_xbrl(t)
    except Exception as e:
        return {"status": "xbrl_download_failed", "err": repr(e)[:60]}
    if not m: return {"status": "xbrl_unparsed", "basis": basis}
    return {"status": "ok", "index": idx, "basis": basis, "created": (x.get("creation_Date") or "")[:20], "m": m, "half": "half" in str(x.get("period") or x.get("type") or "").lower()}

rows = []
for kind, codes in (("stub", stubs), ("valid", vcodes)):
    for c in codes:
        sym = symmap.get(c)
        if not sym:
            rows.append({"code": c, "kind": kind, "status": "no_nse_symbol"}); continue
        r = nse_quarter(sym); r.update(code=c, sym=sym, kind=kind); rows.append(r)
        time.sleep(0.8)

# validation against BSE
from bse import BSE
with BSE(download_folder=tempfile.mkdtemp()) as b:
    q = rf.qcode(2026, 9)
    for r in rows:
        if r["kind"] != "valid" or r.get("status") != "ok": continue
        try: bm = rf.fetch(b, r["code"], "", r["basis"], q)
        except Exception: bm = None
        if not bm: r["cmp"] = "bse_none"; continue
        def close(a, c): return a is not None and c is not None and abs(a - c) <= max(0.05, 0.005 * abs(c))
        nm = r["m"]
        bm = {k: (v / 10.0 if k in ("revenue", "pbt", "pat") and isinstance(v, (int, float)) else v) for k, v in bm.items()}      # BSE table is in Rs million, NSE parse in Rs Cr
        r["cmp"] = "match" if close(nm.get("revenue"), bm.get("revenue")) and close(nm.get("pat"), bm.get("pat")) and close(nm.get("pbt"), bm.get("pbt")) else "MISMATCH"
        r["bse"] = {k: bm.get(k) for k in ("revenue", "pbt", "pat", "eps")}

import collections
for kind in ("stub", "valid"):
    c = collections.Counter(r["status"] for r in rows if r["kind"] == kind)
    p(kind, dict(c))
c = collections.Counter(r.get("cmp") for r in rows if r["kind"] == "valid" and r.get("status") == "ok")
p("validation vs BSE", dict(c))
p("mismatch codes", [r["code"] for r in rows if r.get("cmp") == "MISMATCH"])
okst = [r for r in rows if r["kind"] == "stub" and r["status"] == "ok"]
p("stubs replaceable from NSE", len(okst), "of", len(stubs), "| basis", dict(collections.Counter(r["basis"] for r in okst)), "| half-year records", sum(1 for r in okst if r.get("half")))
os.makedirs("store/stub_dry", exist_ok=True)
json.dump({"qe": QE, "rows": rows}, open("store/stub_dry/result.json", "w"), indent=0)
publish()
