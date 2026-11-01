"""Union two copies of the monthly concall store files by record key, keeping the better record: newer schema version, then a real read over a skip, then the later write time.
usage: store_union.py <mine_dir> <target_dir>   (target_dir files are rewritten; used after a git conflict, target = fresh checkout of origin)"""
import sys, os, json, glob
mine, tgt = sys.argv[1], sys.argv[2]
def rank(r): return (int(str(r.get("v") or 0)) if str(r.get("v") or "0").isdigit() else 0, 0 if r.get("skip") else 1, str(r.get("at") or ""))
names = {os.path.basename(f) for d in (mine, tgt) for f in glob.glob(os.path.join(d, "????-??.jsonl"))}
nrep = nadd = 0
for n in sorted(names):
    recs = {}
    for d, tag in ((tgt, "t"), (mine, "m")):
        fp = os.path.join(d, n)
        if not os.path.exists(fp): continue
        for ln in open(fp, encoding="utf-8"):
            try: r = json.loads(ln)
            except Exception: continue
            k = r.get("key")
            if not k: continue
            if k not in recs: recs[k] = r; nadd += tag == "m"
            elif rank(r) > rank(recs[k]): recs[k] = r; nrep += 1
    rows = sorted(recs.values(), key=lambda r: (r.get("day") or "", r.get("code") or ""))
    with open(os.path.join(tgt, n), "w", encoding="utf-8") as fh:
        for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("union done: files", len(names), "| records from mine added", nadd, "| replaced by better", nrep)
