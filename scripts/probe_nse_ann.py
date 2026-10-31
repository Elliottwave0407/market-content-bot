"""Read-only probe: can NSE corporate announcements (equities + SME) list earnings-call transcripts for any day? Prints counts and field names only."""
import os, re, json, time, collections, requests
from ci_out import p, publish
S = requests.Session()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
try:
    r = S.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", headers={**H, "Accept": "text/html"}, timeout=40); p("warm", r.status_code)
except Exception as e: p("warm err", type(e).__name__)
days = ["14-10-2026", "12-08-2025", "14-11-2024"]
for d in days:
    for idx in ("equities", "sme"):
        url = f"https://www.nseindia.com/api/corporate-announcements?index={idx}&from_date={d}&to_date={d}"
        try:
            r = S.get(url, headers=H, timeout=40)
            if r.status_code != 200: p(d, idx, "status", r.status_code, r.text[:80].replace("\n", " ")); continue
            js = r.json(); rows = js if isinstance(js, list) else js.get("data", [])
            keys = sorted(rows[0].keys()) if rows else []
            desc = collections.Counter((x.get("desc") or "")[:60] for x in rows)
            tr = [x for x in rows if "transcript" in ((x.get("attchmntText") or "") + " " + (x.get("desc") or "")).lower()]
            p(d, idx, "rows", len(rows), "transcript-like", len(tr), "keys", keys[:20])
            p("  top desc:", desc.most_common(6))
            for x in tr[:3]: p("  e.g.", x.get("symbol"), (x.get("desc") or "")[:40], "|", (x.get("attchmntText") or "")[:90].replace("\n", " "), "|", (x.get("attchmntFile") or "")[-40:])
        except Exception as e: p(d, idx, "err", type(e).__name__, str(e)[:80])
        time.sleep(2)
publish()
