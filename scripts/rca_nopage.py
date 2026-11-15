# read-only RCA: why does the reader find no results table page? classifies each filing PDF (posts nothing)
import os, sys, io, re, collections, urllib.request, json
import fitz
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
rows = [l.split() for l in open(os.environ.get("LIST", "state/rca_nopage_urls.txt")) if l.strip()]
shard, nsh = int(os.environ.get("SHARD", 0)), int(os.environ.get("NSH", 1))
rows = rows[shard::nsh]
KW = {"income": r"total\s+income|revenue\s+from\s+operations", "pbt": r"profit.{0,25}before\s+tax", "stmt": r"statement\s+of\s+(un)?audited|financial\s+results", "bm": r"board\s+meeting|intimation", "qtr": r"quarter\s+ended|half\s+year\s+ended|year\s+ended"}
cnt = collections.Counter()
for sym, url in rows:
    try:
        b = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60).read()
        d = fitz.open(stream=b, filetype="pdf")
    except Exception as e:
        cnt["download_fail"] += 1; print("RCA", sym, "download_fail", str(e)[:60]); continue
    n = len(d); tl = []; hits = collections.Counter(); imgp = 0
    for p in d:
        t = p.get_text() or ""; tl.append(len(t))
        if len(t) < 80 and p.get_images(): imgp += 1
        for k, rx in KW.items():
            if re.search(rx, t, re.I): hits[k] += 1
    txt = sum(1 for x in tl if x >= 80)
    if hits["income"] and hits["pbt"]: cause = "table_present_reader_missed"
    elif imgp >= max(1, n // 2): cause = "scanned_image_pages"
    elif hits["bm"] and not hits["income"]: cause = "not_a_results_filing(board_meeting/intimation)"
    elif txt == 0: cause = "no_text_no_images"
    else: cause = "text_but_no_income_rows"
    cnt[cause] += 1
    if cause == "table_present_reader_missed":
        for i, p in enumerate(d):
            t = p.get_text() or ""
            m = re.search(r"[^\n]*(revenue\s+from\s+operations|total\s+income)[^\n]*\n?[^\n]*", t, re.I)
            if m:
                print("RCAPG", sym, "first_income_page_idx=%d" % i, "of", n, "|", repr(m.group(0)[:120])); break
    print("RCA", sym, cause, f"pages={n} textpages={txt} imgpages={imgp}", dict(hits), url.rsplit("/", 1)[-1][:60])
print("RCASUM", json.dumps(cnt))
