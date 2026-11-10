"""Read-only accuracy test of the Groq text reader against filings whose numbers we already posted (from the verified store).
For each sampled filing: download the PDF from BSE, trim it, read it with Groq, run the same arithmetic gate as the live chain, then compare revenue / PBT / PAT / EPS with the stored card numbers.
Posts nothing, writes no state. Env: N (sample size, default 80), SEED, SINCE (YYYY-MM-DD, default 2026-10-20), GAP (seconds between calls, default 9)."""
import os, re, sys, json, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from ci_out import p
import pdf_card as pc
import groq_read as gq

N = int(os.environ.get("N") or "80")
SEED = int(os.environ.get("SEED") or "7")
SINCE = os.environ.get("SINCE") or "2026-10-20"
GAP = float(os.environ.get("GAP") or "9")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
recs = []
for f in ("store/results/2026-10.jsonl", "store/results/2026-11.jsonl"):
    for l in open(f):
        d = json.loads(l)
        if d.get("route") != "bse" or d.get("half_yearly") or (d.get("ts") or "") < SINCE:
            continue
        m = re.search(r"Filing: (\S+)", d.get("caption", ""))
        qs = d.get("quarters") or []
        if not m or not qs or not (qs[0].get("revenue") is not None and qs[0].get("pat") is not None):
            continue
        recs.append((d, m.group(1).rstrip(".,)")))
random.Random(SEED).shuffle(recs)
p(f"candidates {len(recs)}; testing {min(N, len(recs))}")
c = {"tested": 0, "no_pdf": 0, "no_text": 0, "no_answer": 0, "gate_rejected": 0, "unusable": 0, "accepted_match": 0, "accepted_MISMATCH": 0}
mism = []
UA = pc.UA
for d, url in recs[:N]:
    name, truth, basis = d["name"], d["quarters"][0], d["basis"]
    label = d["key"].split("|")[1]
    c["tested"] += 1
    content = b""
    for u in (url, url.replace("AttachLive", "AttachHis"), url.replace("AttachHis", "AttachLive")):
        try:
            r = requests.get(u, headers=UA, timeout=60)
            if r.content[:4] == b"%PDF":
                content = r.content; break
        except Exception:
            pass
    if not content:
        c["no_pdf"] += 1; p(f"{name[:30]} | no pdf"); continue
    small = pc.trim_pdf(content)
    out, err = gq.read_pdf(small)
    time.sleep(GAP)
    if out is None:
        k_ = "no_text" if "no text layer" in str(err) else "no_answer"
        c[k_] += 1; p(f"{name[:30]} | {label} | {k_}: {str(err)[:90]}"); continue
    if pc.arith_fail(out):
        c["gate_rejected"] += 1; p(f"{name[:30]} | {label} | arithmetic gate rejected"); continue
    k = pc.K.get(str(out.get("unit", "")).lower())
    cols = out.get("quarter_end_columns") or []
    qe = pc.parse_qend(cols[0]) if cols else None
    dd = out.get(basis)
    if not k or qe is None or not isinstance(dd, dict) or pc.val(dd, "revenue", 0) is None or pc.val(dd, "pat", 0) is None:
        c["unusable"] += 1; p(f"{name[:30]} | {label} | unusable (unit/date/basis missing; basis {basis})"); continue
    got_label = f"{MON[qe[1] - 1]}-{str(qe[0])[2:]}"
    m = pc.to_m(dd, 0, k)
    bad = []
    if got_label != label: bad.append(f"quarter {got_label} vs {label}")
    for key in ("revenue", "pbt", "pat"):
        a, b = m.get(key), truth.get(key)
        if a is not None and b is not None and not pc.close(a, b): bad.append(f"{key} {a:.2f} vs {b:.2f}")
    a, b = m.get("eps"), truth.get("eps")
    if a is not None and b is not None and abs(a - b) > max(0.06, 0.01 * abs(b)): bad.append(f"eps {a} vs {b}")
    if bad:
        c["accepted_MISMATCH"] += 1; mism.append((name, label, bad)); p(f"{name[:30]} | {label} | MISMATCH: {'; '.join(bad)}")
    else:
        c["accepted_match"] += 1; p(f"{name[:30]} | {label} | match (rev {m['revenue']:.1f} pat {m['pat']:.1f} Cr)")
p("SUMMARY " + json.dumps(c))
acc = c["accepted_match"] + c["accepted_MISMATCH"]
p(f"answered and accepted: {acc}; of those matching the stored numbers: {c['accepted_match']}; mismatches: {c['accepted_MISMATCH']}")
for n_, l_, b_ in mism: p(f"  MISMATCH {n_} {l_}: {b_}")
