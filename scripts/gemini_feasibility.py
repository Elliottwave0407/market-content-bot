"""Test Gemini PDF reading vs BSE table (same 105-filing sample). Needs GEMINI_API_KEY secret."""
import json, os, random, time
from datetime import datetime
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
import gemini_read as gr

DAYS = [datetime(2026, 8, d) for d in (4, 6, 7, 11, 12, 13, 14)]
PER_DAY = int(os.environ.get("PER_DAY", "22"))
MAX_CALLS = int(os.environ.get("MAX_CALLS", "110"))
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "40"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
K = {"lakh": 0.1, "lakhs": 0.1, "crore": 10.0, "crores": 10.0, "million": 1.0, "thousand": 0.001, "actual": 1e-6}
C = ".pdfcache"
os.makedirs(C, exist_ok=True)

def jload(f):
    try: return json.load(open(f))
    except Exception: return None

def ann(bse, **kw):
    for i in range(5):
        try: return bse.announcements(**kw)
        except Exception: time.sleep(5 * (i + 1))
    return {}

def col0(d, k):
    v = (d or {}).get(k)
    return v[0] if isinstance(v, list) and v else None

def close(a, b, k):
    if a is None or b is None: return False
    return abs(a * k - b) <= max(0.051 * max(k, 1), 2e-4 * abs(b), 0.011)

def checks(d):
    ti, ex, pbt, tax, pat = (col0(d, x) for x in ("total_income", "total_expenses", "pbt", "tax", "pat"))
    out = {}
    tol = lambda a, b: abs(a - b) <= max(1.5, 0.002 * max(abs(a), abs(b)))
    if None not in (ti, ex, pbt):
        out["ti_exp_pbt"] = tol(ti - ex, pbt)
    if None not in (pbt, tax, pat):
        out["pbt_tax_pat"] = tol(pbt - tax, pat)
    return out

def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        p("no GEMINI_API_KEY"); return
    models = gr.list_models(key)
    p("available models (flash-ish):", [m for m in models if "flash" in m][:25])
    model = os.environ.get("GEMINI_MODEL") or next((m for m in models if "flash-lite" in m and "preview" not in m and "image" not in m and "tts" not in m), None) or next((m for m in models if "flash" in m), None)
    p("using model:", model)
    t_end = time.time() + BUDGET_MIN * 60
    S, bad, ncalls = {}, [], 0
    def bump(k): S[k] = S.get(k, 0) + 1
    with BSE(download_folder="./") as bse:
        pool = []
        for d in DAYS:
            day, pg, tot = [], 1, 0
            while pg <= 40:
                data = ann(bse, page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t: break
                tot += len(t)
                day += [r for r in t if r.get("CATEGORYNAME") == "Result" and r.get("ATTACHMENTNAME")]
                if tot >= data.get("Table1", [{}])[0].get("ROWCNT", 0): break
                pg += 1
            random.Random(7).shuffle(day)
            pool += day[:PER_DAY]
        for r in pool:
            if time.time() > t_end or ncalls >= MAX_CALLS:
                p("stopped: budget/calls"); break
            code, name, att = str(r["SCRIP_CD"]), r["SLONGNAME"], r["ATTACHMENTNAME"]
            head = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat(r["NEWS_DT"][:19])
            q = rf.expected_quarter(head, filed)
            if q is None: bump("no_quarter"); continue
            truth = jload(f"{C}/{att}.truth.json")
            if truth is None:
                truth = {}
                for basis in ("consolidated", "standalone"):
                    m = rf.fetch(bse, code, name, basis, q)
                    if m and m.get("revenue") is not None and m.get("pat") is not None:
                        truth[basis] = {"revenue": m["revenue"], "pat": m["pat"]}
                json.dump(truth, open(f"{C}/{att}.truth.json", "w"))
            if not truth: bump("no_bse_table"); continue
            content = b""
            for folder in ("AttachLive", "AttachHis"):
                try:
                    resp = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/" + att, headers=UA, timeout=60)
                except Exception:
                    continue
                if resp.content[:4] == b"%PDF": content = resp.content; break
            if not content: bump("not_pdf"); continue
            if len(content) > 15_000_000: bump("too_big"); continue
            ncalls += 1
            t0 = time.time()
            out, err = gr.read_pdf(key, model, content)
            if out is None:
                bump("api_error"); bad.append(f"{name[:24]} API: {err}"); time.sleep(6); continue
            k = K.get(str(out.get("unit", "")).lower())
            res = None
            for basis in ("consolidated", "standalone"):
                d, tr = out.get(basis), truth.get(basis)
                if d and tr and k:
                    ok = close(col0(d, "revenue"), tr["revenue"], k) and close(col0(d, "pat"), tr["pat"], k)
                    ck = checks(d)
                    cp = bool(ck) and all(ck.values()); cf = bool(ck) and not all(ck.values())
                    tag = ("ok" if ok else "WRONG") + ("_chk_pass" if cp else "_chk_fail" if cf else "_chk_na")
                    if res is None or ok: res = tag
                    if not ok and res and res.startswith("WRONG") and len(bad) < 25:
                        bad.append(f"{name[:22]} {basis[:4]} unit={out.get('unit')} got rev={col0(d,'revenue')} pat={col0(d,'pat')} truth(mn) rev={tr['revenue']} pat={tr['pat']} {ck}")
            if res is None:
                res = "no_comparable_basis"
                bad.append(f"{name[:22]} unit={out.get('unit')} keys={[b for b in ('consolidated','standalone') if out.get(b)]} truth_has={list(truth)}")
            bump(res)
            time.sleep(max(0, 5 - (time.time() - t0)))
    n = sum(v for k, v in S.items() if k.startswith(("ok", "WRONG")))
    ok = sum(v for k, v in S.items() if k.startswith("ok"))
    p("SUMMARY:", S)
    p(f"compared {n}: correct {ok} ({100 * ok / max(n, 1):.0f}%), calls {ncalls}")
    for x in bad[:40]: p(x)

try:
    main()
except Exception as e:
    import traceback
    p("Caught error:", repr(e)[:200], traceback.format_exc()[-400:])
publish()
