"""Business taxonomy v0 (26 Nov 2026): group companies by what they actually make or do, from the deep annual report facts (store/annual_report_deep).
Text per company = business description + product names (main revenue lines repeated) + end markets + value-chain position + customers + raw materials.
Two levels: TF-IDF (words and word pairs) + agglomerative clustering on cosine distance gives groups; any group above 12 companies is re-clustered on its own vocabulary into sub-groups.
Peers of a company = its sub-group; if fewer than 3, the parent group. Names are the cluster's top terms until a name is set in taxonomy_names.json (key "G<group>.<sub>" or "G<group>").
usage: python3 scripts/business_taxonomy.py [OUT=/tmp/business_groups.json]   (OUT in the data repo: taxonomy/business_groups.json)"""
import os, sys, json, glob, re, collections, datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "..", "store", "annual_report_deep")
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/business_groups.json"
TOP_THR, SUB_THR, BIG = 0.90, 0.88, 12
STOP = set("""limited company ltd india indian private public group subsidiary subsidiaries business businesses products product services service including includes include offering offers
offered provides provide providing engaged engages manufacturing manufacture manufactures manufacturer sales sale customers customer segment segments various range wide variety solutions solution
leading focus focused year fy ended march also etc across general meeting annual notice agm board directors the and of in to for with its is are as by on from or an a at that which has have their
other others related new based""".split())

def text_of(d):
    f = d.get("facts") or {}; b = f.get("business") or {}
    parts = [b.get("description") or ""]
    for pr in b.get("products") or []:
        n = pr.get("name") or ""; parts.append(n)
        if (pr.get("share_of_revenue_pct") or 0) >= 15: parts.append(n)
    for k in ("end_markets", "customers", "value_chain_position", "raw_materials", "brands_or_certifications"):
        v = b.get(k)
        if isinstance(v, list): parts.extend(str(x) for x in v[:12])
        elif v: parts.append(str(v))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()

def cluster(texts, thr, max_df):
    vec = TfidfVectorizer(stop_words=list(STOP), ngram_range=(1, 2), min_df=2, max_df=max_df, sublinear_tf=True, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b")
    try: X = vec.fit_transform(texts)
    except ValueError: return [0] * len(texts), vec, None
    if len(texts) < 2: return [0] * len(texts), vec, X
    lab = AgglomerativeClustering(n_clusters=None, distance_threshold=thr, metric="cosine", linkage="average").fit(X.toarray()).labels_
    return list(map(int, lab)), vec, X

def top_terms(vec, X, idx, n=6):
    if X is None: return []
    terms = np.array(vec.get_feature_names_out()); cen = np.asarray(X[idx].mean(axis=0)).ravel()
    return [str(t) for t in terms[cen.argsort()[::-1][:n]]]

def main():
    best = {}
    for f in sorted(glob.glob(os.path.join(DIR, "INE*_*.json"))):
        best[os.path.basename(f).split("_")[0]] = f          # latest year wins (sorted)
    docs = []
    for isin, f in best.items():
        try: d = json.load(open(f))
        except Exception: continue
        if not isinstance(d, dict) or not isinstance(d.get("facts"), dict): continue
        t = text_of(d)
        if len(t) >= 60: docs.append({"isin": isin, "name": d.get("name") or isin, "text": t, "fy": d.get("fy")})
    lab, vec, X = cluster([d["text"] for d in docs], TOP_THR, 0.25)
    by = collections.defaultdict(list)
    for i, c in enumerate(lab): by[c].append(i)
    names = {}
    npath = os.path.join(HERE, "taxonomy_names.json")
    if os.path.exists(npath): names = json.load(open(npath))
    groups = []
    for gi, (c, idx) in enumerate(sorted(by.items(), key=lambda kv: -len(kv[1]))):
        g = {"id": "G%d" % gi, "size": len(idx), "terms": top_terms(vec, X, idx), "subgroups": []}
        g["name"] = names.get(g["id"]) or ", ".join(g["terms"][:3])
        if len(idx) > BIG:
            sl, v2, X2 = cluster([docs[i]["text"] for i in idx], SUB_THR, 0.5)
            sub = collections.defaultdict(list)
            for j, c2 in enumerate(sl): sub[c2].append(idx[j])
            parts = [(c2, ids) for c2, ids in sorted(sub.items(), key=lambda kv: -len(kv[1]))]
            for si, (c2, ids) in enumerate(parts):
                loc = [idx.index(i) for i in ids]
                key = "%s.%d" % (g["id"], si); tt = top_terms(v2, X2, loc)
                g["subgroups"].append({"id": key, "size": len(ids), "terms": tt, "name": names.get(key) or ", ".join(tt[:3]), "members": [{"isin": docs[i]["isin"], "name": docs[i]["name"]} for i in ids]})
        else:
            g["subgroups"].append({"id": g["id"] + ".0", "size": len(idx), "terms": g["terms"], "name": g["name"], "members": [{"isin": docs[i]["isin"], "name": docs[i]["name"]} for i in idx]})
        groups.append(g)
    json.dump({"version": "v0", "built": datetime.date.today().isoformat(), "n_companies": len(docs), "groups": groups}, open(OUT, "w"), indent=1)
    subs = [s for g in groups for s in g["subgroups"]]
    sz = collections.Counter(min(s["size"], 6) for s in subs)
    print("companies", len(docs), "| groups", len(groups), "| sub-groups", len(subs), "| sub-group size mix (6 = 6+):", dict(sorted(sz.items())), "| in a sub-group of 3+:", sum(s["size"] for s in subs if s["size"] >= 3))
    for s in sorted(subs, key=lambda s: -s["size"])[:45]:
        print("%2d %-6s %-52s %s" % (s["size"], s["id"], s["name"][:52], "; ".join(m["name"].replace(" Limited", "").replace(" Ltd", "")[:16] for m in s["members"][:3])))

if __name__ == "__main__":
    main()
