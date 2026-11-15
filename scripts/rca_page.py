# read-only RCA: for filings whose text shows a results table, why does the page filter in rule_read not accept it?
import os, sys, re, urllib.request, collections
sys.path.insert(0, "scripts")
import rule_read as rr
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
rows_ = [l.split() for l in open("state/rca_tp_urls.txt") if l.strip()]
sh, n = int(os.environ.get("SHARD", 0)), int(os.environ.get("NSH", 1))
cnt = collections.Counter()
for sym, url in rows_[sh::n]:
    try:
        b = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60).read()
        pages = rr._pdf_rows(b)
    except Exception as e:
        print("PG", sym, "ERR", str(e)[:60]); cnt["err"] += 1; continue
    why = "no_page_has_2_keys"; info = ""
    for pno, (txt, rws) in enumerate(pages):
        low = txt.lower()
        k = sum(x in low for x in rr.KEYS)
        revrows = []
        for r in rws:
            lb, nums = rr.split_row(r)
            c = rr.clean_label(lb)
            if "revenue" in c or "total income" in c or "net sales" in c:
                revrows.append((c[:40], len(nums)))
        if not revrows and k < 2:
            continue
        hasrev = any(n_ >= 3 and any(re.search(p, c_) for p in rr.PAT_REV) for c_, n_ in revrows)
        why = "keys=%d hasrev=%s" % (k, hasrev)
        if k >= 2 and not hasrev:
            why = "rev_row_unmatched"
        elif k < 2 and hasrev:
            why = "keys<2"
        info = "p%d %s" % (pno + 1, revrows[:3])
        if k >= 2 and hasrev:
            why = "PAGE_OK"
            break
    cnt[why.split(" ")[0]] += 1
    print("PG", sym, why, info[:200], flush=True)
print("PGSUM", dict(cnt))
