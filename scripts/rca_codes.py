"""Read-only RCA helper: for BSE scrip codes (env CODES, comma list) filed on DAY (env DAY, YYYY-MM-DD, default today IST), find their Result filings on BSE, print the attachment URLs, and run pdf_url_debug.py on each (row dumps). Posts nothing, writes no state."""
import os, sys, subprocess, tempfile
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bse import BSE
codes = {c.strip() for c in (os.environ.get("CODES") or "").split(",") if c.strip()}
day = os.environ.get("DAY") or (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
d = datetime.fromisoformat(day)
found = {}
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for pg in range(1, 40):
        try:
            data = b.announcements(page_no=pg, from_date=d, to_date=d, category="Result")
        except Exception as e:
            print("fetch error", type(e).__name__, str(e)[:80]); break
        t = data.get("Table", [])
        if not t:
            break
        for r in t:
            if str(r.get("SCRIP_CD")).strip() in codes and r.get("ATTACHMENTNAME"):
                found.setdefault(str(r["SCRIP_CD"]).strip(), []).append(r)
print("found", {k: len(v) for k, v in found.items()}, "of", sorted(codes), flush=True)
for code, rs in found.items():
    for r in rs[:2]:
        url = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/" + r["ATTACHMENTNAME"]
        print("\n######", code, r.get("SLONGNAME"), (r.get("HEADLINE") or "")[:90], url, flush=True)
        env = dict(os.environ, URL=url, HINT=(r.get("HEADLINE") or ""), QHINT="")
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_url_debug.py")], env=env, capture_output=True, text=True, timeout=900)
        out = (p.stdout or "") + (p.stderr or "")
        print(out[-9000:], flush=True)
