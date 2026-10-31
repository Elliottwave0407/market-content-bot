import json, re, requests, collections
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
S.get("https://www.nseindia.com/", headers=H, timeout=40)
rows = [json.loads(l) for l in open("store/results_if_dry/filings.jsonl", encoding="utf-8")]
r = rows[0]; u = r["xbrl"]; resp = S.get(u, headers=H, timeout=60); p(r["sym"], r["to"], resp.status_code, len(resp.text), u[-60:])
t = resp.text; p("head", re.sub(r"\s+", " ", t[:600]))
ctx = re.findall(r"<(?:\w+:)?context\s+id=\"([^\"]+)\"(.*?)</(?:\w+:)?context>", t, re.S); p("contexts", len(ctx), [(c, re.findall(r">(\d{4}-\d\d-\d\d)<", b)) for c, b in ctx[:6]])
facts = re.findall(r"<([\w\-]+):([A-Za-z0-9_]+)\s[^>]*contextRef=\"([^\"]+)\"[^>]*>([^<]*)<", t); p("facts", len(facts), "prefixes", collections.Counter(f[0] for f in facts).most_common(5))
for ns, tag, c, v in facts[:60]: p("  ", ns, tag, c[:25], v[:25])
publish()
