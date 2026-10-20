"""Dry run: find official earnings-call transcripts filed on BSE, score each as a possible 'story', print a ranked shortlist.
Nothing is posted anywhere. Score is computed in code from facts Gemini extracts; every fact must carry a quote that exists in the transcript."""
import os, sys, re, io, json, time, tempfile, traceback
from datetime import datetime, timedelta
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import recap_post as rp
import news_posts as NP
import store

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_SCAN_MODEL", "").strip() or "gemini-flash-lite-latest"
_IST = datetime.utcnow() + timedelta(hours=5, minutes=30)
if os.environ.get("DAYS_BACK"):       # scheduled mode: a rolling window ending today (IST)
    D0 = (_IST - timedelta(days=int(os.environ["DAYS_BACK"]))).strftime("%Y-%m-%d"); D1 = _IST.strftime("%Y-%m-%d")
else:
    D0 = os.environ.get("FROM_DAY", "2026-10-06")
    D1 = os.environ.get("TO_DAY", "2026-10-16")
MAX_N = int(os.environ.get("MAX_N", "15"))
MCAP_MAX = float(os.environ.get("MCAP_MAX", "100000000"))   # Rs Cr; default = every company (smallest are extracted first)
BASE = "https://generativelanguage.googleapis.com/v1beta"

PROMPT = """You read the transcript of an Indian listed company's earnings conference call. Extract ONLY what management actually said. Never infer or add outside knowledge.
Return ONLY JSON:
{"company":"","quarter":"",
 "ebitda_margin":{"current_pct":number,"compare_pct":number,"compare_basis":"yoy|qoq","quote":""} or null,
 "margin_outlook":{"direction":"expand|stable|contract","detail":"","quote":""} or null,
 "rev_yoy_pct":{"value":number,"quote":""} or null,
 "pat_yoy_pct":{"value":number,"quote":""} or null,
 "guidance":[{"metric":"","detail":"","quote":""}],
 "order_book":{"detail":"","quote":""} or null,
 "capex":[{"detail":"amount and purpose","funding":"internal accruals|debt|equity|mixed|not stated","timeline":"","quote":""}],
 "capacity":[{"detail":"","quote":""}],
 "mix":[{"detail":"share of premium / value-added / new products and how it is changing","direction":"premium_up|premium_down|neutral","quote":""}],
 "moat":[{"type":"only_player|licence_approval|ip_technology|backward_integration|switching_cost|scale|brand|other","detail":"why competitors cannot easily copy it, as management said","quote":""}],
 "catalysts":[{"type":"order|acquisition|launch|other","detail":"","quote":""}],
 "risks":[{"type":"working_capital|margin|concentration|debt|other_income|regulatory|execution|other","detail":"","quote":""}],
 "not_said":["important things an investor would want that management did not give, e.g. no margin guidance"],
 "one_line":"<=20 words: the single most important takeaway"}
Rules: every quote is VERBATIM from the transcript, at most 25 words, and must support the item. detail is plain English, one short line, numbers exactly as spoken. Max 4 items per list. Fill ebitda_margin only if management gave the margin numbers; do not compute it yourself. moat only if management described a real barrier (not just 'we are good')."""

DBG = []

def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()

def quote_ok(q, text_tokens_set4):
    t = norm(q)
    if len(t) < 4:
        if os.environ.get("DEBUG_Q") and len(DBG) < 14:
            DBG.append(f"short/empty quote: {str(q)[:60]!r}")
        return False
    grams = [" ".join(t[i:i + 4]) for i in range(len(t) - 3)]
    hit = sum(1 for g in grams if g in text_tokens_set4)
    r = hit / len(grams)
    if r < 0.7 and os.environ.get("DEBUG_Q") and len(DBG) < 14:
        DBG.append(f"{round(r, 2)} | {q[:140]}")
    return r >= 0.7

def pdf_text(url):
    from pypdf import PdfReader
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    if r.status_code != 200 or len(r.content) > 12_000_000:
        return None
    rd = PdfReader(io.BytesIO(r.content))
    return " ".join((pg.extract_text() or "") for pg in rd.pages)

def gem(text):
    body = {"contents": [{"parts": [{"text": PROMPT + "\n\nTRANSCRIPT:\n" + text[:300000]}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for i in range(4):
        r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers={"x-goog-api-key": KEY}, json=body, timeout=240)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (i + 1)); continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        try:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```json|```$", "", t.strip())), None
        except Exception as e:
            return None, "parse " + repr(e)[:60]
    return None, "rate/5xx"

def sanitize(f):
    """Gemini sometimes returns one item as a bare object, or a list where an object is expected."""
    for k in ("guidance", "capex", "capacity", "mix", "moat", "catalysts", "risks"):
        v = f.get(k)
        if isinstance(v, dict):
            f[k] = [v]
        elif not isinstance(v, list):
            f[k] = []
        else:
            f[k] = [x for x in v if isinstance(x, dict)]
    for k in ("ebitda_margin", "margin_outlook", "order_book", "rev_yoy_pct", "pat_yoy_pct"):
        v = f.get(k)
        if isinstance(v, list):
            f[k] = v[0] if v and isinstance(v[0], dict) else None
        elif not isinstance(v, dict):
            f[k] = None
    if not isinstance(f.get("not_said"), list):
        f["not_said"] = []
    return f

def mcaps():
    """BSE scrip code -> (market cap Rs Cr, group). Each group is retried (BSE sometimes drops a group), and the last good values are cached in state/mcap_cache.json as a fallback."""
    from bse import BSE
    CF = "state/mcap_cache.json"
    try: cache = json.load(open(CF))
    except Exception: cache = {}
    out = {}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y"):
            for attempt in range(3):
                try:
                    rows = b.listSecurities(group=g)
                    if not rows and attempt < 2:
                        time.sleep(3); continue
                    for x in rows:
                        try:
                            v = float(str(x.get("Mktcap") or "0").replace(",", ""))
                        except Exception:
                            v = 0
                        out[str(x.get("SCRIP_CD")).strip()] = (v, g)
                    break
                except Exception:
                    time.sleep(3)
    fresh = {k: v for k, v in out.items() if v[0] > 0}
    for k, v in cache.items():
        if k not in fresh:
            out[k] = (v[0], v[1])
    try:
        json.dump({**cache, **{k: [v[0], v[1]] for k, v in fresh.items()}}, open(CF, "w"))
    except Exception:
        pass
    return out

def find_transcripts():
    rows = []
    d = datetime.fromisoformat(D0)
    end = datetime.fromisoformat(D1)
    while d <= end:
        if d.weekday() < 5:
            try:
                for x in rp._fetch_day(d):
                    txt = " ".join(str(x.get(k) or "") for k in ("NEWSSUB", "HEADLINE", "MORE")).lower()
                    sub = x.get("SUBCATNAME") or ""
                    if not x.get("ATTACHMENTNAME"):
                        continue
                    is_tr = sub == "Earnings Call Transcript" or ("transcript" in txt and ("earnings" in txt or "conference call" in txt or "investor call" in txt))
                    if is_tr and not any(w in txt for w in ("annual general", "agm", "webinar", "postal ballot")):
                        rows.append(x)
            except Exception as e:
                p("fetch err", d.date(), repr(e)[:50])
        d += timedelta(days=1)
    seen, out = set(), []
    for x in rows:
        k = (x.get("SCRIP_CD"), (x.get("NEWS_DT") or "")[:10])
        if k not in seen:
            seen.add(k); out.append(x)
    return out

def score(f, ok):
    """ok(q)->bool verifies a quote. 100 pts: margin 25, capex/capacity 20, mix 20, moat 15, growth+visibility 15, clarity 5; risks subtract up to 20."""
    def good(item):
        return isinstance(item, dict) and ok(item.get("quote"))
    def lst(k):
        return [x for x in (f.get(k) or []) if good(x)]
    # margin
    mg = 0
    em = f.get("ebitda_margin")
    if good(em) and isinstance(em.get("current_pct"), (int, float)) and isinstance(em.get("compare_pct"), (int, float)) and 0 < em["current_pct"] < 100 and 0 < em["compare_pct"] < 100:
        d = em["current_pct"] - em["compare_pct"]
        mg += 15 if d >= 5 else 12 if d >= 3 else 8 if d >= 1 else 4 if d >= 0 else 0
    mo = f.get("margin_outlook")
    if good(mo):
        mg += {"expand": 10, "stable": 5}.get(mo.get("direction"), 0)
    mg = min(25, mg)
    # capex & capacity
    cx, cp = lst("capex"), lst("capacity")
    internal = any("internal" in str(x.get("funding", "")).lower() for x in cx)
    cpx = min(20, 6 * len(cx) + 5 * len(cp) + (4 if internal else 0))
    # product mix
    mx = min(20, sum({"premium_up": 8, "neutral": 3}.get(x.get("direction"), 0) for x in lst("mix")))
    # moat
    mt = min(15, 5 * len(lst("moat")))
    # growth + visibility
    ys = [it["value"] for it in (f.get("rev_yoy_pct"), f.get("pat_yoy_pct")) if good(it) and isinstance(it.get("value"), (int, float))]
    g = 0
    if ys:
        m = max(ys)
        g = 8 if m >= 50 else 6 if m >= 25 else 4 if m >= 10 else 2 if m >= 0 else 0
    gd = lst("guidance")
    ob = f.get("order_book") if good(f.get("order_book")) else None
    vis = min(7, 3 * min(len(gd), 2) + (3 if ob else 0))
    gv = g + vis
    clar = min(5, len(gd) + (1 if ob else 0) + (1 if em and good(em) else 0))
    rk = lst("risks")
    pen = min(20, 4 * len(rk))
    total = max(0, mg + cpx + mx + mt + gv + clar - pen)
    parts = {"margin": mg, "capex": cpx, "mix": mx, "moat": mt, "growth_visibility": gv, "clarity": clar, "risk_penalty": -pen}
    facts = {"ebitda_margin": [em] if good(em) else [], "margin_outlook": [mo] if good(mo) else [], "capex": cx, "capacity": cp, "mix": lst("mix"), "moat": lst("moat"), "guidance": gd, "order_book": [ob] if ob else [], "catalysts": lst("catalysts"), "risks": rk}
    return total, parts, facts

def main():
    os.makedirs("out", exist_ok=True)
    tr = find_transcripts()
    p("transcript filings found", len(tr), D0, "->", D1)
    mc = mcaps()
    p("market-cap list", len(mc), "nonzero", sum(1 for v, _ in mc.values() if v > 0))
    for x in tr[:8]:
        k = str(x.get("SCRIP_CD")).strip(); p("  mcap check", k, (x.get("SLONGNAME") or "")[:22], mc.get(k))
    cand = []
    for x in tr:
        code = str(x.get("SCRIP_CD")).strip()
        v, g = mc.get(code, (0, "?"))
        x["_mc"], x["_g"] = v, g
        if v and v > MCAP_MAX:
            continue
        cand.append(x)
    p("after size filter (<= Rs", int(MCAP_MAX), "Cr or unknown):", len(cand))
    for x in tr:       # every transcript filing seen is kept, scored or not
        try:
            store.put("concall_filings", f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}", {"code": str(x.get("SCRIP_CD")).strip(), "name": (x.get("SLONGNAME") or "").strip(), "filed": (x.get("NEWS_DT") or "")[:19], "headline": (x.get("HEADLINE") or x.get("NEWSSUB") or "")[:300], "link": NP.link(x), "mcap_cr": x.get("_mc"), "group": x.get("_g")}, month=(x.get("NEWS_DT") or "")[:7] or None)
        except Exception:
            pass
    # raw transcript text is kept for EVERY company's call (cheap, no Gemini); extraction below is limited by the free quota
    nraw = 0
    for x in tr:
        code = str(x.get("SCRIP_CD")).strip(); day = (x.get("NEWS_DT") or "")[:10]
        if not day or os.path.exists(os.path.join(store.ROOT, "concall_text", f"{code}_{day}.txt.gz")):
            continue
        try:
            t_ = pdf_text(NP.link(x))
            if t_ and len(t_) >= 5000 and store.put_text("concall_text", f"{code}_{day}", t_):
                nraw += 1
        except Exception:
            pass
    p("raw transcripts newly saved:", nraw)
    done_keys = set()
    try:
        import glob
        for fp in glob.glob(os.path.join(store.ROOT, "concalls", "*.jsonl")):
            for ln in open(fp, encoding="utf-8"):
                try: done_keys.add(json.loads(ln)["key"])
                except Exception: pass
    except Exception:
        pass
    cand = [x for x in cand if f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}" not in done_keys]
    cand.sort(key=lambda x: x["_mc"] or 0)       # smallest companies first (unknown size first)
    cand = cand[:MAX_N]
    res = []
    for x in cand:
        name = (x.get("SLONGNAME") or "").strip()
        try:
            txt = pdf_text(NP.link(x))
        except Exception as e:
            p("pdf err", name[:25], repr(e)[:40]); continue
        if not txt or len(txt) < 5000:
            p("skip (no text / scanned)", name[:30]); continue
        toks = norm(txt)
        grams = set(" ".join(toks[i:i + 4]) for i in range(len(toks) - 3))
        f, err = gem(txt)
        if f:
            f = sanitize(f) if isinstance(f, dict) else None
        if f and os.environ.get("DEBUG_Q") and "Asset" in name:
            p("RAW", json.dumps(f)[:1800])
        if not f:
            p("gemini fail", name[:25], err); continue
        ok = lambda q: quote_ok(q, grams)
        total, parts, facts = score(f, ok)
        nclaims = sum(len(f.get(k) or []) for k in ("guidance", "catalysts", "risks", "capex", "capacity", "mix", "moat")) + sum(1 for k in ("order_book", "ebitda_margin", "margin_outlook") if f.get(k))
        nver = sum(len(v) for k, v in facts.items() if k in ("guidance", "catalysts", "risks", "capex", "capacity", "mix", "moat", "order_book", "ebitda_margin", "margin_outlook"))
        res.append({"name": name, "code": x.get("SCRIP_CD"), "mcap": x["_mc"], "grp": x["_g"], "total": total, "parts": parts, "facts": facts, "f": f, "claims": nclaims, "verified": nver, "words": len(txt.split())})
        p("scored", name[:30], total)
        try:
            day = (x.get("NEWS_DT") or "")[:10]; code = str(x.get("SCRIP_CD")).strip()
            tp = store.put_text("concall_text", f"{code}_{day}", txt)
            store.put("concalls", f"{code}|{day}", {"code": code, "name": name, "filed": (x.get("NEWS_DT") or "")[:19], "link": NP.link(x), "mcap_cr": x["_mc"], "group": x["_g"], "words": len(txt.split()),
                      "model": MODEL, "score": total, "score_parts": parts, "claims": nclaims, "verified_claims": nver, "extracted": f, "verified_facts": facts, "transcript_file": tp}, month=day[:7] or None)
        except Exception as e:
            p("store err", repr(e)[:60])
        time.sleep(4)
    for d_ in DBG:
        p("FAILQ", d_)
    res.sort(key=lambda r: -r["total"])
    lines = []
    for i, r in enumerate(res, 1):
        pt = r["parts"]; fa = r["facts"]
        lines.append(f"#{i} {r['name']} ({r['code']}) | mcap Rs {int(r['mcap']):,} Cr | SCORE {r['total']}/100")
        lines.append(f"   margin {pt['margin']}/25 | capex {pt['capex']}/20 | mix {pt['mix']}/20 | moat {pt['moat']}/15 | growth+visibility {pt['growth_visibility']}/15 | clarity {pt['clarity']}/5 | risks {pt['risk_penalty']}")
        lines.append(f"   facts verified in transcript: {r['verified']} of {r['claims']} claimed")
        lines.append(f"   story: {r['f'].get('one_line')}")
        for k, tag in (("ebitda_margin", "MARGIN"), ("margin_outlook", "MARGIN OUTLOOK"), ("capex", "CAPEX"), ("mix", "MIX"), ("moat", "MOAT")):
            for it in fa[k][:2]:
                if k == "ebitda_margin":
                    lines.append(f"   + {tag}: {it.get('current_pct')}% vs {it.get('compare_pct')}% ({it.get('compare_basis')})" if it.get('compare_pct') is not None else f"   + {tag}: {it.get('current_pct')}% (no comparison given)")
                else:
                    lines.append(f"   + {tag}: {it.get('detail')}" + (f" [funding: {it.get('funding')}]" if k == "capex" else ""))
        for k in fa["risks"][:2]:
            lines.append(f"   - {k.get('type')}: {k.get('detail')}")
        for n in (r["f"].get("not_said") or [])[:2]:
            lines.append(f"   ? not said: {n}")
    for l in lines:
        p(l)
    open("out/scan_shortlist.txt", "w").write("\n".join(lines))
    json.dump([{k: v for k, v in r.items() if k != "f"} for r in res], open("out/scan.json", "w"), default=str)

try:
    main()
except Exception:
    p("ERR", traceback.format_exc()[-1200:])
publish()
