"""Test the label-based PDF reader (pdf_results) against BSE tables. Caches PDFs/rows/truth in .pdfcache."""
import json, os, random, time
from datetime import datetime
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
import pdf_results as pr

DAYS = [datetime(2026, 8, d) for d in (4, 6, 7, 11, 12, 13, 14)]
PER_DAY = int(os.environ.get("PER_DAY", "22"))
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "32"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.bseindia.com/"}
DIAG = ("Safari Ind", "Alembic", "Advent Hotels", "Medi Caps", "PG Electro", "Belrise", "Tavexia", "Gopal Snacks")
DONE = set()
C = ".pdfcache"
os.makedirs(C, exist_ok=True)

def jload(f):
    try:
        return json.load(open(f))
    except Exception:
        return None

def jsave(f, o):
    json.dump(o, open(f, "w"))

def close(parsed, k, decs, truth):
    if parsed is None or truth is None:
        return False
    tol = max(0.51 * (10 ** -decs) * k, 2e-4 * abs(truth), 0.011)
    return abs(parsed * k - truth) <= tol

def ann(bse, **kw):
    for i in range(5):
        try:
            return bse.announcements(**kw)
        except Exception:
            time.sleep(5 * (i + 1))
    return {}

def main():
    t_end = time.time() + BUDGET_MIN * 60
    S, wrong, rows = {}, [], []
    def bump(k): S[k] = S.get(k, 0) + 1
    with BSE(download_folder="./") as bse:
        pool = []
        for d in DAYS:
            day, pg, tot = [], 1, 0
            while pg <= 40:
                data = ann(bse, page_no=pg, from_date=d, to_date=d)
                t = data.get("Table", [])
                if not t:
                    break
                tot += len(t)
                day += [r for r in t if r.get("CATEGORYNAME") == "Result" and r.get("ATTACHMENTNAME")]
                if tot >= data.get("Table1", [{}])[0].get("ROWCNT", 0):
                    break
                pg += 1
            random.Random(7).shuffle(day)
            pool += day[:PER_DAY]
        p(f"sampled filings: {len(pool)}")
        for r in pool:
            if time.time() > t_end:
                p("time budget reached"); break
            code, name, att = str(r["SCRIP_CD"]), r["SLONGNAME"], r["ATTACHMENTNAME"]
            head = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat(r["NEWS_DT"][:19])
            q = rf.expected_quarter(head, filed)
            if q is None:
                bump("no_quarter"); continue
            tf = f"{C}/{att}.truth.json"
            truth = jload(tf)
            if truth is None:
                truth = {}
                for basis in ("consolidated", "standalone"):
                    m = rf.fetch(bse, code, name, basis, q)
                    if m and m.get("revenue") is not None and m.get("pat") is not None:
                        truth[basis] = {"revenue": m["revenue"], "pat": m["pat"], "prev": None, "yago": None}
                jsave(tf, truth)
            if not truth:
                bump("no_bse_table"); continue
            rf_ = f"{C}/{att}.rows.json"
            cached = jload(rf_)
            if cached is None:
                content = b""
                try:
                    for folder in ("AttachLive", "AttachHis"):
                        resp = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/" + att, headers=UA, timeout=60)
                        if resp.content[:4] == b"%PDF":
                            content = resp.content; break
                    if not content:
                        bump("not_pdf"); continue
                    pages, ocrp, rows_ = pr.extract_rows(content)
                except Exception as e:
                    bump("pdf_error"); continue
                cached = {"pages": pages, "ocr": ocrp, "rows": rows_}
                jsave(rf_, cached)
            if any(k in name for k in DIAG) and name not in DONE:
                DONE.add(name)
                rr = cached["rows"]
                idx = [i for i, x in enumerate(rr) if any(w in " ".join(x).lower() for w in ("revenue from op", "total income", "net sales"))][:1]
                i0 = idx[0] if idx else 0
                p(f"## RAW {name[:28]} pages={cached['pages']} ocr={cached['ocr']} nrows={len(rr)}")
                for x in rr[max(0, i0 - 4): i0 + 14]:
                    p("   ", " | ".join(x)[:150])
            tables = pr.parse(cached["rows"])
            if cached["ocr"]: bump("ocr_files")
            good = [t for t in tables if "rev" in t["vals"] and "pat" in t["vals"]]
            if not good:
                bump("not_parsed"); rows.append(f"{name[:24]:24} NOT_PARSED tables={len(tables)} ocr={cached['ocr']}"); continue
            sel = next((t for t in good if t["basis"] == "consolidated"), None) or next((t for t in good if t["basis"] == "standalone"), None) or good[0]
            ck = pr.checks(sel)
            ck_pass = bool(ck) and all(ck.values())
            ck_fail = bool(ck) and not all(ck.values())
            if sel["unit"] is None:
                bump("unit_unknown")
            k = sel["unit"][1] if sel["unit"] else None
            def eval_table(t, basis):
                tr = truth.get(basis)
                if not tr:
                    return None
                ks = [t["unit"][1]] if t["unit"] else [0.1, 10.0, 1.0]
                for kk in ks:
                    (rv, rd), (pv, pd) = t["vals"]["rev"][0], t["vals"]["pat"][0]
                    if close(rv, kk, rd, tr["revenue"]) and close(pv, kk, pd, tr["pat"]):
                        return True
                return False
            res = eval_table(sel, sel["basis"]) if sel["basis"] in truth else None
            if res is None:
                # basis not known or truth only has the other basis: try any
                anyok = any(eval_table(t, b) for t in good for b in truth)
                bump("basis_ambiguous_ok" if anyok else "basis_ambiguous_bad")
                if not anyok:
                    wrong.append(f"{name[:22]} basis={sel['basis']} truth_has={list(truth)} unit={sel['unit'] and sel['unit'][0]} parsed rev={sel['vals']['rev'][0][0]} pat={sel['vals']['pat'][0][0]} truth={ {b: (v['revenue'], v['pat']) for b, v in truth.items()} }")
                continue
            tag = ("ok" if res else "WRONG") + ("_chk_pass" if ck_pass else ("_chk_fail" if ck_fail else "_chk_na"))
            bump(tag)
            if not res:
                tr = truth[sel["basis"]]
                wrong.append(f"{name[:22]} {sel['basis']} unit={sel['unit'] and sel['unit'][0]} ocr={cached['ocr']} parsed rev={sel['vals']['rev'][0][0]} pat={sel['vals']['pat'][0][0]} truth(mn) rev={tr['revenue']} pat={tr['pat']} {ck}")
    n = sum(v for k, v in S.items() if k.startswith(("ok", "WRONG", "basis_")))
    ok = sum(v for k, v in S.items() if k.startswith("ok") or k == "basis_ambiguous_ok")
    p("SUMMARY:", S)
    p(f"evaluated {n}: correct {ok} ({100 * ok / max(n, 1):.0f}%)  not_parsed {S.get('not_parsed', 0)}")
    for x in wrong[:40]:
        p("WRONG:", x)
    for x in rows[:30]:
        p(x)

try:
    main()
except Exception as e:
    import traceback
    p("Caught error:", repr(e)[:300], traceback.format_exc()[-500:])
publish()
