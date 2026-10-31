"""Read-only probe: what does NSE give for (a) quarterly financial results, (b) investor presentations, per day / period? Prints counts and field names only."""
import os, json, time, collections, requests
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"}
S.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", headers={**H, "Accept": "text/html"}, timeout=40)
def get(url):
    try:
        r = S.get(url, headers=H, timeout=45)
        if r.status_code != 200: p("  status", r.status_code, r.text[:100].replace("\n", " ")); return None
        return r.json()
    except Exception as e: p("  err", type(e).__name__, str(e)[:80]); return None
for idx in ("equities", "sme"):
    for per in ("Quarterly",):
        u = f"https://www.nseindia.com/api/corporates-financial-results?index={idx}&period={per}&from_date=01-10-2026&to_date=15-10-2026"
        js = get(u); p(idx, per, "->", type(js).__name__, len(js) if js else 0)
        if js and isinstance(js, list) and js:
            p("  keys", sorted(js[0].keys())); p("  sample", {k: (str(v)[:70]) for k, v in list(js[0].items())[:25]})
# structured numbers per company?
for u in ("https://www.nseindia.com/api/results-comparision?symbol=INFY", "https://www.nseindia.com/api/quote-equity?symbol=INFY&section=trade_info"):
    js = get(u); p(u.split("/api/")[1][:50], "->", type(js).__name__, (list(js.keys())[:10] if isinstance(js, dict) else (len(js) if js else 0)))
# investor presentations in announcements
for d in ("14-11-2024", "12-08-2025"):
    for idx in ("equities", "sme"):
        js = get(f"https://www.nseindia.com/api/corporate-announcements?index={idx}&from_date={d}&to_date={d}")
        rows = js if isinstance(js, list) else (js or {}).get("data", [])
        c = collections.Counter((x.get("desc") or "")[:50] for x in rows)
        ip = [x for x in rows if "presentation" in ((x.get("desc") or "") + " " + (x.get("attchmntText") or "")).lower()]
        p(d, idx, "rows", len(rows), "presentation-like", len(ip), "desc 'Investor Presentation':", c.get("Investor Presentation", 0))
        for x in ip[:2]: p("   e.g.", x.get("symbol"), (x.get("desc") or "")[:30], "|", (x.get("attchmntText") or "")[:70], "|", (x.get("attchmntFile") or "")[-45:])
        time.sleep(2)
publish()
