"""Read-only: for every result filing that got a STUB card (posted key 'code|quarter|na'), ask BSE again whether structured numbers exist now.
Counts how many stubs could be upgraded to full cards by the normal path. Sends nothing, no Gemini, no state change."""
import os, sys, json, re, traceback
from datetime import datetime
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
import results_fetcher as rf
try:
    rpl.DAYS_BACK = int(os.environ.get("DAYS", "10"))
    st = json.load(open("state/seen.json")); mc = json.load(open("state/mcap_cache.json"))
    stub = {k.split("|")[0]: k.split("|")[1] for k in st["posted"] if k.endswith("|na")}
    p("stub keys in state:", len(stub))
    with BSE(download_folder="/tmp") as b:
        rows = rpl.fetch_filings(b)
        seen = {}
        for r in rows:
            c = str(r.get("SCRIP_CD")).strip()
            if c in stub and (c not in seen or r["NEWS_DT"] < seen[c]["NEWS_DT"]): seen[c] = r
        p("stub filings found in the last", rpl.DAYS_BACK, "days:", len(seen))
        out = []; cnt = Counter()
        for c, r in seen.items():
            name = r["SLONGNAME"]; headline = (r.get("NEWSSUB") or "") + " " + (r.get("HEADLINE") or "")
            filed = datetime.fromisoformat(r["NEWS_DT"][:19])
            try:
                res = rf.results_for_filing(b, c, name, headline, filed)
                if res["status"] == "quarter_unverified":
                    res = rf.results_for_filing(b, c, name, headline + " quarter ended " + rpl.inferred_qend(filed), filed)
                s = res["status"]
            except Exception as e:
                s = "error " + type(e).__name__
            cnt[s] += 1
            out.append((mc.get(c, [0])[0], name[:26], c, r["NEWS_DT"][5:16], s))
        p("status now:", dict(cnt))
        for m, n, c, d, s in sorted(out, reverse=True)[:40]:
            p(f"{n} ({c}) mcap {m:,.0f} cr | filed {d} | {s}")
except Exception:
    p("ERROR", traceback.format_exc()[-900:])
publish()
