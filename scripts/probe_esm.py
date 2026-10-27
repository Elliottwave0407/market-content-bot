"""Read-only probe: where do NSE and BSE publish the live ESM (Enhanced Surveillance Measure) lists, and can a GitHub runner reach them? Loads the exchange pages in a headless browser and records the data requests the pages make. Sends nothing, changes nothing."""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from playwright.sync_api import sync_playwright
PAGES = ["https://www.nseindia.com/static/regulations/enhanced-surveillance-measure-esm",
         "https://www.bseindia.com/markets/equity/EQReports/enhanced_surveillance_measure.aspx"]
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for url in PAGES:
            ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
            pg = ctx.new_page(); seen = []
            def on_resp(r, seen=seen):
                u = r.url
                if any(k in u.lower() for k in ("esm", "surveil", "api/", "json", ".csv", ".xls", "download")) and "google" not in u and "analytics" not in u:
                    try: seen.append((r.status, u[:200], (r.text() or "")[:160].replace("\n", " ") if r.status == 200 and ("json" in (r.headers.get("content-type") or "") or "csv" in u) else ""))
                    except Exception: seen.append((r.status, u[:200], ""))
            pg.on("response", on_resp)
            try:
                pg.goto(url, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(4000)
            except Exception as e:
                p("goto problem", url[:60], type(e).__name__)
            p("PAGE", url[:90], "| title:", pg.title()[:60], "| text sample:", pg.inner_text("body")[:300].replace("\n", " | "))
            for s in seen[:25]: p("  req", s[0], s[1], s[2])
            links = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href).filter(h => /esm|surveil|\\.csv|\\.xls|\\.pdf/i.test(h))")
            p("  links:", links[:20])
            ctx.close()
        b.close()
except Exception:
    p("ERROR", traceback.format_exc()[-600:])
publish()
