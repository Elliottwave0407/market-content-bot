"""Concall SUPPLEMENT pass: for transcripts already read (schema v3 or older) extract ONLY the five added topics
(promoter, auditor_governance, related_party, cash_flow, dilution). Results go to a separate store (store/concall_supp), keyed like
concall_facts (code|day), so nothing already stored is touched; the company page merges both by key.
Every item must carry a word-for-word quote from the transcript (same verify() as the main reader).
Order: smallest companies first (market cap from store/mcap/mcap.json; unknown = treated as small).
Env: N (max transcripts, default 16), BUDGET_MIN, OUT_DIR (default concall_supp), MODELS, DRY=1 prints only."""
import os, sys, re, json, time, glob
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SCHEMA_V", "4")
from ci_out import p, publish
import store
import concall_extract as CE
import concall_themes as CT

N = int(os.environ.get("N") or "16")
BUDGET = float(os.environ.get("BUDGET_MIN") or "60")
OUT = os.path.join(store.ROOT, os.environ.get("OUT_DIR") or "concall_supp")
DRY = os.environ.get("DRY") == "1"
T0 = time.time()

SUPP = """You read an Indian listed company's earnings-call transcript. Extract ONLY what MANAGEMENT (not analysts) said about these five topics. Return ONLY JSON:
{"items":[{"cat":"<one category>","statement":"short plain summary (max 30 words)","period":"e.g. FY27, Q3 FY26, next quarter, or null","value":"number or range exactly as stated, or null","direction":"up|down|flat|null","quote":"ONE or TWO consecutive sentences copied character for character from the transcript (keep filler words, do not shorten, join or paraphrase, no ellipses), under 250 characters"}]}
Categories: promoter (promoter holding change, pledge or encumbrance, stake sale or purchase, promoter buying, creeping acquisition), auditor_governance (auditor change or resignation, audit qualification or emphasis of matter, delayed filings, internal-control or fraud issues, regulator or exchange queries, board or CFO exits), related_party (related-party transactions, loans or advances to promoter entities, group-company dealings), cash_flow (operating cash flow, free cash flow, receivables or debtor build-up, advances, capex funding, cash and bank balance), dilution (preferential issue, warrants, QIP, rights issue, ESOP, equity or convertible raise, fresh share issue, price and size).
Rules: up to 12 items, only these five categories, only what is actually said. Every quote must be copied word for word. The statement may say ONLY what the quote says (no added units, scope, timing or comparisons; do not report that something was NOT said). Do not invent numbers. If none of the five topics is discussed, return {"items":[]}. No investment advice."""

CE.PROMPT = SUPP
CE.MAXTOK = 3500
KEEP = {"promoter", "auditor_governance", "related_party", "cash_flow", "dilution"}


def mcap_by_code():
    out = {}
    try:
        d = json.load(open(os.path.join(store.ROOT, "mcap", "mcap.json")))
        for v in d.values():
            if v.get("m") is None:
                continue
            if v.get("s") is not None:
                out[str(v["s"]).strip()] = v.get("m")
            if v.get("n"):
                out["NSE:" + str(v["n"]).strip().upper()] = v.get("m")
    except Exception as e:
        p("mcap map missing:", e)
    return out


def load_out():
    d = {}
    for f in glob.glob(os.path.join(OUT, "????-??.jsonl")):
        for ln in open(f, encoding="utf-8"):
            try:
                r = json.loads(ln); d[r["key"]] = r
            except Exception:
                pass
    return d


def save_out(d):
    os.makedirs(OUT, exist_ok=True)
    by = {}
    for r in d.values():
        by.setdefault((r.get("day") or "0000-00")[:7], []).append(r)
    for m, rows in by.items():
        rows.sort(key=lambda r: (r.get("day") or "", r.get("code") or ""))
        tmp = os.path.join(OUT, m + ".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, os.path.join(OUT, m + ".jsonl"))


def one(r):
    base = {"key": r["key"], "code": r["code"], "name": r.get("name"), "day": r["day"], "v": "supp1", "src": r["src"]}
    txt = CT.pdf_text(r["src"])
    if not txt:
        return {**base, "skip": "no_text"}
    t = CE.prep(txt)
    raw, used, bad = [], None, 0
    cs = CE.chunks(t)
    for ch in cs:
        got = None
        for m in CE.MODELS:
            got = CE.call(m, ch)
            if got is not None:
                used = used or m.split("/")[-1]; break
        if got is None:
            bad += 1; continue
        raw += got.get("items") or []
    if bad == len(cs):
        return None
    raw = [i for i in raw if isinstance(i, dict) and str(i.get("cat") or "") in KEEP]
    ok = CE.verify(raw, t)
    return {**base, "words": len(t.split()), "model": used, "n_raw": len(raw), "n_ok": len(ok), "items": ok,
            "at": time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 19800))}


def main():
    if not CE.NV and not CE.MK:
        p("no model key"); return
    p("models:", ", ".join(m.split("/")[-1] for m in CE.MODELS), "N", N, "out", os.path.basename(OUT), "dry" if DRY else "live")
    main_done = CE.load_done()
    done = load_out()
    mc = mcap_by_code()
    todo = [r for r in main_done.values() if not r.get("skip") and r.get("src") and r["key"] not in done and str(r.get("v")) != "4"]
    UNK = 5000.0      # unknown market cap (crore) sorts after the known small caps and before the bigger companies
    todo.sort(key=lambda r: (mc.get(str(r["code"]).strip(), UNK), r.get("day") or ""))
    p("transcripts already read:", len(main_done), "| supplement todo:", len(todo), "| done:", len(done))
    if DRY:
        for r in todo[:10]:
            p(" next:", r["code"], r.get("name"), r["day"], "mcap", mc.get(str(r["code"]).strip(), "?"))
        return
    pick = todo[:N]; n_ok = n_items = n_skip = n_fail = 0; times = []
    with ThreadPoolExecutor(CE.WORKERS) as ex:
        futs = {ex.submit(one, r): r for r in pick}
        for f in as_completed(futs):
            t1 = time.time()
            try:
                res = f.result()
            except Exception as e:
                p("error", futs[f]["key"], repr(e)[:120]); res = None
            if res is None:
                n_fail += 1; continue
            done[res["key"]] = res
            if res.get("skip"): n_skip += 1
            else: n_ok += 1; n_items += res.get("n_ok", 0)
            if (time.time() - T0) / 60 > BUDGET:
                p("budget reached"); break
    save_out(done)
    left = max(0, len(todo) - n_ok - n_skip)
    st = {"remaining": left if os.environ.get("AUTO") == "1" else 0, "progressed": n_ok + n_skip, "real_remaining": left}
    json.dump(st, open(os.path.join(OUT, "_state.json"), "w"))
    mins = (time.time() - T0) / 60
    p(f"supplement: read {n_ok} | items {n_items} | skipped {n_skip} | failed {n_fail} | {mins:.1f} min | {mins / max(1, n_ok):.1f} min per transcript (workers {CE.WORKERS})")
    cats = {}
    for r in done.values():
        for i in r.get("items") or []:
            cats[i["cat"]] = cats.get(i["cat"], 0) + 1
    p("items by category:", cats)


if __name__ == "__main__":
    main()
