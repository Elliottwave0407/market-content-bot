"""Season replay: run the FAST rule/OCR reader on real filings of a result season and compare with NSE's own XBRL numbers (the truth set).
Read-only: posts nothing, writes only out/replay_<shard>.json. Env: START, END (YYYY-MM-DD, NSE filing days), SHARD, NSHARDS, MAXN (filings per shard), PERIOD (qe prefix, default 30-sep-2026), QHINT (BSE quarter code, 131 = Sep-26)."""
import os, sys, json, time, re
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["RULE_OCR"] = "1"; os.environ["NSE_SME"] = "1"
import nse_results as nr, fin_data as fd, rule_read as rr, pdf_card as pc

START, END = os.environ.get("START", "2026-11-10"), os.environ.get("END", "2026-11-14")
SHARD, NSH = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARDS", "1"))
MAXN = int(os.environ.get("MAXN", "60"))
PERIOD = os.environ.get("PERIOD", "30-sep-2026"); QH = int(os.environ.get("QHINT", "131"))
OUT = os.environ.get("OUT_DIR", "out"); os.makedirs(OUT, exist_ok=True)

d0, d1 = datetime.strptime(START, "%Y-%m-%d"), datetime.strptime(END, "%Y-%m-%d")
rows, day = [], d0
while day <= d1:
    for x in nr.result_rows(nr.fetch_day(day.replace(tzinfo=nr.IST))):
        rows.append(x)
    day += timedelta(days=1)
by = {}
for x in rows:
    by.setdefault(x["symbol"], x)
syms = sorted(by)
mine = [s for i, s in enumerate(syms) if i % NSH == SHARD][:MAXN]
print(f"filings {len(rows)} symbols {len(syms)} shard {SHARD}/{NSH} -> {len(mine)}", flush=True)
sess = nr.sess()

def truth_for(sym):
    data = []
    for idx in ("equities", "sme"):
        try:
            r = sess.get("https://www.nseindia.com/api/integrated-filing-results", params={"index": idx, "symbol": sym}, headers=fd.REF_I, timeout=30)
            data = r.json().get("data", []) if r.status_code == 200 and r.text.strip() else []
        except Exception:
            data = []
        if data: break
    best = {}
    for y in data:
        if "Financial" not in (y.get("type") or "") or y.get("xbrl") in (None, "None"): continue
        if not str(y.get("qe_Date") or "").lower().startswith(PERIOD): continue
        b = "consolidated" if y.get("consolidated") == "Consolidated" else "standalone"
        if b not in best or (y.get("creation_Date") or "") >= (best[b].get("creation_Date") or ""): best[b] = y
    out = {}
    for b, y in best.items():
        try:
            m = fd.parse_xbrl(sess.get(y["xbrl"], headers={"Referer": "https://www.nseindia.com/"}, timeout=45).text)
        except Exception:
            m = None
        if m and m.get("revenue") is not None and m.get("pat") is not None:
            out[b] = {"revenue": m["revenue"] * 10, "pat": m["pat"] * 10}      # Rs Cr -> Rs million
    return out

def close(a, b, rel=0.02, ab=0.5):
    return abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))

res = []
for sym in mine:
    x = by[sym]; rec = {"symbol": sym, "an_dt": x.get("an_dt"), "file": x.get("attchmntFile")}
    t0 = time.time()
    try:
        c = b""
        for att in range(3):
            r = sess.get(x["attchmntFile"], headers={"Referer": nr.REF}, timeout=60)
            c = r.content
            if c[:4] == b"%PDF": break
            time.sleep(1)
        if c[:4] != b"%PDF":
            rec["outcome"] = "no_pdf"; res.append(rec); continue
        rec["mb"] = round(len(c) / 1e6, 1)
        small = pc.trim_pdf(c) if len(c) > 1_000_000 else c
        t1 = time.time()
        out, err = rr.read_pdf(small, x.get("attchmntText") or "", QH)
        if out is None and small is not c and len(c) <= 40_000_000:
            out, err = rr.read_pdf(c, x.get("attchmntText") or "", QH)
        rec["read_secs"] = round(time.time() - t1, 1)
        tr = truth_for(sym)
        rec["truth_bases"] = sorted(tr)
        if out is None:
            rec["outcome"] = "no_parse:" + re.sub(r"\d+", "N", (err or "")[:60])
            print("FAIL", sym, x.get("attchmntFile"), "|", (err or "")[:420].replace("\n", " "), flush=True)
        else:
            k = pc.K.get(str(out.get("unit", "")).lower())
            got = {}
            for b in ("consolidated", "standalone"):
                d = out.get(b)
                if isinstance(d, dict) and k:
                    cur = pc.to_m(d, 0, k)
                    if cur.get("revenue") is not None and cur.get("pat") is not None:
                        got[b] = {"revenue": cur["revenue"], "pat": cur["pat"]}
            rec["read_bases"] = sorted(got); rec["ocr"] = bool(out.get("_ocr"))
            if not tr:
                rec["outcome"] = "no_truth"
            else:
                want = "consolidated" if "consolidated" in tr else "standalone"
                if want == "consolidated" and "consolidated" not in got and "standalone" in got:
                    rec["outcome"] = "WRONG_BASIS"
                elif want in got and close(got[want]["revenue"], tr[want]["revenue"]) and close(got[want]["pat"], tr[want]["pat"], 0.03, 1.0):
                    rec["outcome"] = "match"
                elif want in got:
                    rec["outcome"] = "MISMATCH"; rec["detail"] = {"read": got[want], "truth": tr[want]}
                else:
                    rec["outcome"] = "no_parse:wanted basis not read"
    except Exception as e:
        rec["outcome"] = "error:" + repr(e)[:60]
    rec["secs"] = round(time.time() - t0, 1)
    res.append(rec)
    print(sym, rec["outcome"], rec.get("read_secs"), flush=True)
json.dump(res, open(os.path.join(OUT, f"replay_{SHARD}.json"), "w"), indent=1)
import collections
c = collections.Counter(r["outcome"].split(":")[0] if r["outcome"].startswith("no_parse") else r["outcome"] for r in res)
print("SUMMARY", dict(c), flush=True)
nps = collections.Counter(r["outcome"] for r in res if r["outcome"].startswith("no_parse"))
print("NOPARSE", dict(nps), flush=True)
