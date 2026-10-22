"""P1 read-only probes: (1) what fields BSE's security list carries (sector/industry?), (2) which Gemini models the '-latest' aliases point to. Spends no meaningful quota."""
import os, sys, tempfile, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests

try:
    from bse import BSE
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "X"):
            try:
                rows = b.listSecurities(group=g)
            except Exception as e:
                p("listSecurities", g, "error", repr(e)[:80]); continue
            p("group", g, "rows", len(rows))
            if rows:
                p("keys:", sorted(rows[0].keys()))
                p("sample:", json.dumps(rows[0], default=str)[:600])
                ind = [r for r in rows if r.get("INDUSTRY") or r.get("Industry") or r.get("SECTOR") or r.get("Sector")]
                p("rows with an industry/sector field:", len(ind))
                inds = sorted({str(r.get("INDUSTRY") or r.get("Industry") or r.get("SECTOR") or r.get("Sector")) for r in ind})
                p("distinct industry values:", len(inds), inds[:25])
        try:
            p("BSE helper methods mentioning industry/sector:", [m for m in dir(b) if any(w in m.lower() for w in ("industry", "sector", "peer", "scrip", "quote", "profile"))][:30])
        except Exception:
            pass
except Exception:
    p("BSE probe error", traceback.format_exc()[-800:])

try:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=30)
    ms = [m for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    p("gemini models with generateContent:", len(ms))
    for m in ms:
        n = m["name"].split("/")[-1]
        if "latest" in n or "flash" in n:
            p(n, "|", m.get("displayName"), "| in", m.get("inputTokenLimit"), "out", m.get("outputTokenLimit"), "| v", m.get("version"))
except Exception:
    p("gemini probe error", traceback.format_exc()[-600:])
publish()
