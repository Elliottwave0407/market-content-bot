"""Investor-presentation VISION pass (pilot, separate store, changes no stored fact, posts nothing).
Numbers that sit only in charts/images are invisible to the text reader. For each presentation, the pages the text pass flagged as visual (record field visual_slides)
are cut into a small PDF and read by Gemini (vision). Items are stored in store/ppt_vision with src="vision": there is no text layer to verify a quote against,
so every vision item is UNVERIFIED until the independent judge (ppt_audit) checks it; nothing from this store is used or published before that.
Env: N (presentations, default 10), MAX_PAGES (default 8), KEY_ENV (default GEMINI_API_KEY_CONCALL), DAY_FROM (default 2026-10-01), BUDGET_MIN."""
import os, sys, re, json, time, glob, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests, store

N = int(os.environ.get("N") or "10"); MAXP = int(os.environ.get("MAX_PAGES") or "8"); BUDGET = float(os.environ.get("BUDGET_MIN") or "25")
KEY = os.environ.get(os.environ.get("KEY_ENV") or "GEMINI_API_KEY_CONCALL", "").strip()
MODELS = [m for m in (os.environ.get("VISION_MODELS") or "gemini-flash-lite-latest,gemini-flash-latest").split(",") if m]
DAY_FROM = os.environ.get("DAY_FROM") or "2026-10-01"
OUT = os.path.join(store.ROOT, "ppt_vision"); os.makedirs(OUT, exist_ok=True)
T0 = time.time()
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*"}
PROMPT = """These are slides (charts, tables, images) from an Indian listed company's investor presentation. Extract concrete numbers the COMPANY shows that are drawn in charts or images: revenue, EBITDA, margins, PAT, order book, capacity, KPIs, guidance, segment splits.
Return ONLY JSON: {"items":[{"slide":<page number in THIS file starting at 1>,"cat":"results|segment|guidance|order_book|capex|capacity|kpi|balance_sheet|other","statement":"short plain summary (max 25 words)","period":"e.g. Q2 FY27, FY26, or null if not shown","value":"number exactly as shown, with unit as shown, or null","what_you_see":"the label or title next to the number as printed"}]}
Rules: only numbers you can actually read on the slide; if a value is unclear, leave it out; never calculate or estimate; state the period only if the slide shows it; up to 20 items."""

def call(pdf):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}}, {"text": PROMPT}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 5000}}
    last = None
    for m in MODELS:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=120)
        except Exception as e:
            last = f"timeout {m}"; continue
        if r.status_code != 200:
            last = f"HTTP {r.status_code} {m}"; continue
        try:
            mm = re.search(r"\{.*\}", r.json()["candidates"][0]["content"]["parts"][0].get("text", ""), re.S)
            return json.loads(mm.group(0)).get("items") or [], m, None
        except Exception as e:
            last = "parse " + repr(e)[:50]
    return None, None, last

def main():
    import fitz
    if not KEY: p("no key"); return
    done = set()
    for f in glob.glob(os.path.join(OUT, "v_*.jsonl")):
        for l in open(f, encoding="utf-8"):
            try: done.add(json.loads(l)["key"])
            except Exception: pass
    recs = []
    for f in sorted(glob.glob(os.path.join(store.ROOT, "ppt_facts", "20*.jsonl")), reverse=True):
        for l in open(f, encoding="utf-8"):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("visual_slides") and r.get("url") and r["key"] not in done and (r.get("day") or "") >= DAY_FROM and r.get("pages", 0) <= 80: recs.append(r)
    recs.sort(key=lambda r: (len(r["visual_slides"]) > 40, -len(r.get("items") or []) if False else 0, r["day"]), reverse=False)
    p("candidates:", len(recs), "| this run:", N)
    out = open(os.path.join(OUT, f"v_{time.strftime('%Y-%m-%d_%H%M')}.jsonl"), "w", encoding="utf-8")
    n_ok = n_fail = n_items = 0; fails = {}
    for r in recs[:N]:
        if (time.time() - T0) / 60 > BUDGET: break
        try:
            c = requests.get(r["url"], headers=UA, timeout=60).content
            if c[:4] != b"%PDF": n_fail += 1; fails["no_pdf"] = fails.get("no_pdf", 0) + 1; continue
            src = fitz.open(stream=c, filetype="pdf"); pages = [s for s in r["visual_slides"] if s <= src.page_count][:MAXP]
            dst = fitz.open()
            for s in pages: dst.insert_pdf(src, from_page=s - 1, to_page=s - 1)
            items, model, err = call(dst.tobytes())
        except Exception as e:
            items, model, err = None, None, repr(e)[:60]
        if items is None:
            n_fail += 1; fails[str(err)[:30]] = fails.get(str(err)[:30], 0) + 1; time.sleep(3); continue
        for it in items:
            s = it.get("slide")
            it["orig_slide"] = pages[s - 1] if isinstance(s, int) and 0 < s <= len(pages) else None
        n_ok += 1; n_items += len(items)
        out.write(json.dumps({"key": r["key"], "name": r["name"], "day": r["day"], "url": r["url"], "src": "vision", "model": model, "pages_sent": pages, "items": items}, ensure_ascii=False) + "\n"); out.flush()
        time.sleep(4)
    out.close()
    p(f"read {n_ok} | failed {n_fail} {fails} | vision items {n_items} | items per presentation {n_items / max(1, n_ok):.1f} | {(time.time() - T0) / 60:.1f} min")
    publish()

main()
