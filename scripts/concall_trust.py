"""Trust grade for EVERY stored concall fact (A / B / C). Free, no AI calls, read-only on the facts. Output: store/concall_trust/grades.json
{ "<code>|<day>": {"m": "<reader> v<schema>", "g": "ABAC..."}}  one letter per item, in the order of the stored items; plus store/concall_trust/summary.json.

Every stored fact already has its quote verified to exist in the transcript (that is how the extractor keeps it). The grade says how much to trust the SUMMARY/value on top of that quote:
  A = no issues. B = exactly one issue. C = two or more issues, or a question-style quote (possible analyst voice), or the independent judge said the quote does not support the statement.
Issues: stmt_nums (a number in the summary is not in the quote), value_nums (the value field has a number not in the quote), realigned (quote text had to be re-aligned to the transcript),
        old_schema (schema v1 reader: weaker audit results), short_quote (< 40 chars), no_period (forward-looking category with no period).
The independent judge (store/concall_audit): 'partial' caps at B, 'no' forces C. Rules are written so they can be shown on a website."""
import os, sys, re, json, glob, collections
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
NUM = re.compile(r"\d[\d,]*\.?\d*")
def nums(s): return {n.replace(",", "").rstrip(".") for n in NUM.findall(s or "")}
def group(r):
    m = str(r.get("model", "?")).split("/")[-1].replace("-latest", "")
    return f"{m} v{r.get('v', 1)}"

judge = {}
for f in glob.glob(os.path.join(ROOT, "concall_audit", "audit_*.json")):
    try:
        for x in json.load(open(f, encoding="utf-8")):
            if x.get("support") in ("partial", "no"):
                k = (x.get("key"), (x.get("statement") or "")[:80])
                if judge.get(k) != "no": judge[k] = x["support"]
    except Exception: pass

out, issues_ct, grade_ct, by_reader = {}, collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
for f in sorted(glob.glob(os.path.join(ROOT, "concall_facts", "20*.jsonl"))):
    for l in open(f, encoding="utf-8"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("skip") or not r.get("items"): continue
        g_, letters = group(r), []
        for it in r["items"]:
            q = it.get("quote") or ""; v = str(it.get("value") or ""); st = it.get("statement") or ""
            iss = []
            st2 = re.sub(r"\b(FY|CY|H|Q)\s?-?\d{1,4}\b|\b(19|20)\d\d\b|\b\d{1,2}(st|nd|rd|th)\b", " ", st)
            qn = q.replace(",", "")
            if any(n.strip(".,").replace(",", "") not in qn for n in re.findall(r"\d[\d.,]*", st2) if len(n.strip(".,")) >= 2): iss.append("stmt_nums")
            if v and nums(v) and not nums(v) <= nums(q): iss.append("value_nums")
            if it.get("realigned"): iss.append("realigned")
            if str(r.get("v", 1)) == "1": iss.append("old_schema")
            if len(q) < 40: iss.append("short_quote")
            if not it.get("period") and it.get("cat") in ("guidance", "capex", "order_book"): iss.append("no_period")
            n = len(iss)
            grade = "A" if n == 0 else ("B" if n == 1 else "C")
            if "?" in q: grade = "C"; iss.append("question")
            j = judge.get((r.get("key"), st[:80]))
            if j == "no": grade = "C"; iss.append("judge_no")
            elif j == "partial" and grade == "A": grade = "B"; iss.append("judge_partial")
            for i in iss: issues_ct[i] += 1
            grade_ct[grade] += 1; by_reader[g_][grade] += 1; letters.append(grade)
        out[r["key"]] = {"m": g_, "g": "".join(letters)}
os.makedirs(os.path.join(ROOT, "concall_trust"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "concall_trust", "grades.json"), "w"), separators=(",", ":"))
tot = sum(grade_ct.values())
summ = {"documents": len(out), "facts": tot, "grades": dict(grade_ct), "issues": dict(issues_ct), "by_reader": {k: dict(v) for k, v in by_reader.items()}}
json.dump(summ, open(os.path.join(ROOT, "concall_trust", "summary.json"), "w"), indent=1)
print(json.dumps(summ, indent=1)); print({k: f"{v/tot:.1%}" for k, v in grade_ct.items()})
