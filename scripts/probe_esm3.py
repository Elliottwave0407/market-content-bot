"""Read-only: list NSE SURVEILLANCE circulars about ESM (2025-2026) and print the text of the newest 'Revision/Applicability' ones, to confirm the CURRENT entry criteria (is the 'peer standard deviation' still there?)."""
import os, sys, io, json, time, re, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*"}
try:
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25)
    rows = []
    for a, b in (("01-07-2025", "31-12-2025"), ("01-01-2026", "27-10-2026")):
        r = s.get(f"https://www.nseindia.com/api/circulars?fromDate={a}&toDate={b}&department=SURVEILLANCE", headers={"Referer": "https://www.nseindia.com/resources/exchange-communication-circulars"}, timeout=40)
        d = r.json().get("data", []) if r.status_code == 200 else []
        p("circulars", a, b, r.status_code, len(d))
        rows += d
    esm = [x for x in rows if re.search(r"enhanced surveillance|\bESM\b", (x.get("sub") or "") + (x.get("circDisplayNo") or ""), re.I)]
    p("ESM circulars:", len(esm), "| keys:", sorted(rows[0].keys()) if rows else None)
    other = [x for x in esm if "Applicability" not in (x.get("sub") or "")]
    p("non-Applicability ESM circulars:", len(other))
    for x in sorted(other, key=lambda x: x.get("cirDate", ""))[-12:]:
        p(" ", x.get("cirDisplayDate"), x.get("circDisplayNo"), "|", (x.get("sub") or "")[:120], "|", x.get("circFilelink"))
    import pdfplumber
    app = sorted([x for x in esm if "Applicability" in (x.get("sub") or "")], key=lambda x: x.get("cirDate", ""))
    targets = [x for x in sorted(other, key=lambda x: x.get("cirDate", ""))[-2:]] + [app[-1]]
    for x in targets:
        try:
            rr = requests.get(x["circFilelink"], headers=UA, timeout=40)
            p("=== fetch", x.get("cirDisplayDate"), x.get("circDisplayNo"), rr.status_code, len(rr.content), rr.content[:6], x["circFilelink"][-40:])
            with pdfplumber.open(io.BytesIO(rr.content)) as f:
                txt = " ".join((pg.extract_text() or "") for pg in f.pages).replace("\n", " ")
            for i in range(0, min(len(txt), 3500), 700): p(txt[i:i + 700])
        except Exception as e:
            p("pdf error", repr(e)[:80])
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
