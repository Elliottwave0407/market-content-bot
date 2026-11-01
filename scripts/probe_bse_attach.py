"""Read-only: why do some BSE presentation PDFs not download? Tries AttachLive vs AttachHis and header variants on sample no_download records."""
import os, sys, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p, publish
import store
rs = [json.loads(l) for f in sorted(glob.glob(os.path.join(store.ROOT, "ppt_facts", "20*.jsonl"))) for l in open(f, encoding="utf-8")]
nd = [r for r in rs if r.get("status") == "no_download" and r.get("exch") == "bse"]
p("no_download bse:", len(nd), "of", len(rs))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
s = requests.Session()
try: s.get("https://www.bseindia.com/", headers=H, timeout=30)
except Exception as e: p("warm failed", type(e).__name__)
for r in nd[:8] + nd[-4:]:
    u = r["url"]; out = []
    for tag, url in (("Live", u), ("His", u.replace("AttachLive", "AttachHis"))):
        for hv, hd in (("ref", {**H, "Referer": "https://www.bseindia.com/"}), ("plain", H)):
            try:
                x = s.get(url, headers=hd, timeout=40); out.append(f"{tag}/{hv}:{x.status_code}:{len(x.content)}:{x.content[:4]!r}")
            except Exception as e: out.append(f"{tag}/{hv}:{type(e).__name__}")
    p(r["day"], r["name"][:22], " | ".join(out))
publish()
