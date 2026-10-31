import json, re, time, requests, collections
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
S.get("https://www.nseindia.com/", headers=H, timeout=40)
rows = [json.loads(l) for l in open("store/results_hist/filings.jsonl", encoding="utf-8")]
pick = [r for r in rows if r["sym"] in ("INFY", "HDFCBANK", "TCS", "20MICRONS") and r["to"].endswith("2024") and "Dec" in r["to"]][:5]
for r in pick:
    u = r["xbrl"]; resp = S.get(u, headers=H, timeout=60)
    p(r["sym"], r["cons"], r["to"], resp.status_code, len(resp.text), u[-40:])
    if resp.status_code != 200: continue
    txt = resp.text
    tags = re.findall(r"<(?:in-capmkt|in-bse-fin|[A-Za-z\-]+):([A-Za-z0-9_]+)[^>]*contextRef=\"([^\"]+)\"[^>]*>([^<]*)<", txt)
    c = collections.Counter(t for t, _, _ in tags); p("  tags", len(tags), "unique", len(c))
    want = ("Revenue", "Income", "Profit", "Tax", "Expenses", "Depreciation", "Finance", "EarningsPerShare", "Cost", "Employee")
    shown = 0
    for t, ctx, v in tags:
        if any(w in t for w in want) and shown < 40: p("   ", t, ctx[:30], v[:25]); shown += 1
publish()
