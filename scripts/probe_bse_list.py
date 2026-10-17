import sys, os, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
chk = {"INE669C01036": "TECHM", "INE732I01013": "ANGELONE", "INE421D01014": "CCL", "INE255Z01019": "E2E", "INE900B01011": "KABRA", "INE205B01023": "ELECON"}
seen = {}
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y", "F", "G", "W", "SS", "ST", "XD", "XC"):
        try:
            rows = b.listSecurities(group=g)
            p("group", g, len(rows), "keys", sorted(rows[0].keys())[:14] if rows else "")
            for x in rows:
                i = (x.get("ISIN_NUMBER") or "").strip()
                if i in chk:
                    seen[i] = g
        except Exception as e:
            p("group", g, "error", repr(e)[:90])
    for kw in ({}, {"status": "Active"}):
        try:
            rows = b.listSecurities(**kw)
            p("no-group call", kw, len(rows))
        except Exception as e:
            p("no-group call", kw, "error", repr(e)[:90])
p("found:", {chk[i]: g for i, g in seen.items()}, "missing:", [chk[i] for i in chk if i not in seen])
publish()
