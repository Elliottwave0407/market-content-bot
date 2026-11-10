import os, json, tempfile, datetime as dt, requests
from bse import BSE
CODE = os.environ.get("SCRIP", "533339")
out = "companydata/" + os.environ.get("SYMBOL", "zen").lower() + "_q2" if os.environ.get("SYMBOL") != "ZENTEC" else "companydata/zen_q2"; os.makedirs(out, exist_ok=True)
a, z = dt.datetime(2026, 10, 20), dt.datetime.now()
rows = []
with BSE(download_folder=tempfile.mkdtemp()) as b:
    for pg in range(1, 5):
        d = b.announcements(page_no=pg, from_date=a, to_date=z, scripcode=CODE)
        t = d.get("Table", [])
        if not t: break
        rows += t
for x in sorted(rows, key=lambda x: x.get("NEWS_DT") or ""):
    print((x.get("NEWS_DT") or "")[:16], "|", x.get("SUBCATNAME"), "|", (x.get("HEADLINE") or x.get("NEWSSUB") or "")[:110].replace("\n", " "), "|", x.get("ATTACHMENTNAME"))
json.dump(rows, open(out + "/ann.json", "w"))
from pypdf import PdfReader
for x in rows:
    h = ((x.get("HEADLINE") or "") + (x.get("NEWSSUB") or "")).lower()
    if x.get("ATTACHMENTNAME") and ("transcript" in h or "conference call" in h or "recording" in h or "presentation" in h):
        u = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/" + x["ATTACHMENTNAME"]
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}, timeout=60)
            fn = out + "/" + x["ATTACHMENTNAME"]
            open(fn, "wb").write(r.content)
            if fn.lower().endswith(".pdf"):
                txt = "\n".join((p.extract_text() or "") for p in PdfReader(fn).pages)
                open(fn + ".txt", "w").write(txt)
                print("saved", fn, len(txt), "chars;", h[:60])
        except Exception as e:
            print("dl err", repr(e)[:80])
