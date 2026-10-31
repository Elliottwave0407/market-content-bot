import re, requests, fitz
from ci_out import p, publish
import pdf_card as pc
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Referer": "https://www.nseindia.com/"}
S.get("https://www.nseindia.com/", headers=H, timeout=40)
c = S.get("https://nsearchives.nseindia.com/corporate/ZENTEC_31102026162542_BM_OC_UFR_Q2FY26.pdf", headers=H, timeout=90).content
d = fitz.open(stream=c, filetype="pdf"); p("pages", d.page_count, "KEYS", pc.KEYS)
hits = []
for i in range(d.page_count):
    t = d[i].get_text().lower()
    n = sum(k in t for k in pc.KEYS)
    if n >= 2: hits.append(i)
    p(" page", i + 1, "keyhits", n, "chars", len(t), "consolidated" in t, "standalone" in t, re.sub(r"\s+", " ", t[:90]))
keep = sorted(set(hits[:4]) | {min(hits[0] + 1, d.page_count - 1)}) if hits else []
p("hits", [h + 1 for h in hits], "kept after trim", [k + 1 for k in keep])
publish()
