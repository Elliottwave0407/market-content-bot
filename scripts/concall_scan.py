"""Dry run: find official earnings-call transcripts filed on BSE, score each as a possible 'story', print a ranked shortlist.
Nothing is posted anywhere. Score is computed in code from facts Gemini extracts; every fact must carry a quote that exists in the transcript."""
import os, sys, re, io, json, time, tempfile, traceback
from datetime import datetime, timedelta
import requests
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import recap_post as rp
import news_posts as NP

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_SCAN_MODEL", "").strip() or "gemini-flash-lite-latest"
D0 = os.environ.get("FROM_DAY", "2026-10-06")
D1 = os.environ.get("TO_DAY", "2026-10-16")
MAX_N = int(os.environ.get("MAX_N", "15"))
MCAP_MAX = float(os.environ.get("MCAP_MAX", "25000"))   # Rs Cr; focus = SME / micro / small
BASE = "https://generativelanguage.googleapis.com/v1beta"

PROMPT = """You read the transcript of an Indian listed company's earnings conference call. Extract ONLY what management actually said. Never infer or add outside knowledge.
Return ONLY JSON:
{"company":"","quarter":"",
 "rev_yoy_pct":{"value":number,"quote":""} or null,
 "pat_yoy_pct":{"value":number,"quote":""} or null,
 "guidance":[{"metric":"","detail":"","quote":""}],
 "order_book":{"detail":"","quote":""} or null,
 "catalysts":[{"type":"order|capex|capacity|acquisition|launch|other","detail":"","quote":""}],
 "risks":[{"type":"working_capital|margin|concentration|debt|other_income|regulatory|execution|other","detail":"","quote":""}],
 "not_said":["important things an investor would want that management did not give, e.g. no margin guidance"],
 "tone":"confident|neutral|cautious","one_line":"<=20 words: the single most important takeaway"}
Rules: every quote is VERBATIM from the transcript, at most 25 words, and must support the item. detail is plain English, one short line, numbers exactly as spoken. Max 5 items per list. yoy values only if management said the growth figure or it is stated plainly; otherwise null."""

def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()

def quote_ok(q, text_tokens_set4):
    t = norm(q)
    if len(t) < 4:
        return False
    grams = [" ".join(t[i:i + 4]) for i in range(len(t) - 3)]
    hit = sum(1 for g in grams if g in text_tokens_set4)
    return hit / len(grams) >= 0.7

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

def mcaps():
    from bse import BSE
    out = {}
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y"):
            try:
                for x in b.listSecurities(group=g):
                    try:
                        v = float(str(x.get("Mktcap") or "0").replace(",", ""))
                    except Exception:
                        v = 0
                    out[str(x.get("SCRIP_CD")).strip()] = (v, g)
            except Exception:
                continue
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
    """ok(q)->bool verifies a quote. Returns (total, parts, verified facts)."""
    def good(item):
        return isinstance(item, dict) and ok(item.get("quote"))
    g = 0
    ys = []
    for k in ("rev_yoy_pct", "pat_yoy_pct"):
        it = f.get(k)
        if good(it) and isinstance(it.get("value"), (int, float)):
            ys.append(it["value"])
    if ys:
        m = max(ys)
        g = 25 if m >= 100 else 20 if m >= 50 else 14 if m >= 25 else 8 if m >= 10 else 3 if m >= 0 else 0
    gd = [x for x in (f.get("guidance") or []) if good(x)]
    ob = f.get("order_book") if good(f.get("order_book")) else None
    vis = min(25, 8 * min(len(gd), 2) + (9 if ob else 0))
    cat = [x for x in (f.get("catalysts") or []) if good(x)]
    cats = min(25, 7 * len(cat))
    clar = min(15, 5 * len(gd) + (5 if ob else 0))
    tone = {"confident": 10, "neutral": 5, "cautious": 0}.get(f.get("tone"), 5) if ok(f.get("tone_quote", "x" * 40)) or True else 5
    rk = [x for x in (f.get("risks") or []) if good(x)]
    pen = min(20, 4 * len(rk))
    total = max(0, g + vis + cats + clar + tone - pen)
    return total, {"growth": g, "visibility": vis, "catalysts": cats, "clarity": clar, "tone": tone, "risk_penalty": -pen}, {"guidance": gd, "order_book": ob, "catalysts": cat, "risks": rk}

def main():
    os.makedirs("out", exist_ok=True)
    tr = find_transcripts()
    p("transcript filings found", len(tr), D0, "->", D1)
    mc = mcaps()
    p("market-cap list", len(mc))
    cand = []
    for x in tr:
        code = str(x.get("SCRIP_CD")).strip()
        v, g = mc.get(code, (0, "?"))
        x["_mc"], x["_g"] = v, g
        if v and v > MCAP_MAX:
            continue
        cand.append(x)
    p("after size filter (<= Rs", int(MCAP_MAX), "Cr or unknown):", len(cand))
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
        if not f:
            p("gemini fail", name[:25], err); continue
        ok = lambda q: quote_ok(q, grams)
        total, parts, facts = score(f, ok)
        nclaims = sum(len(f.get(k) or []) for k in ("guidance", "catalysts", "risks")) + (1 if f.get("order_book") else 0)
        nver = sum(len(v) if isinstance(v, list) else (1 if v else 0) for v in facts.values())
        res.append({"name": name, "code": x.get("SCRIP_CD"), "mcap": x["_mc"], "grp": x["_g"], "total": total, "parts": parts, "facts": facts, "f": f, "claims": nclaims, "verified": nver, "words": len(txt.split())})
        p("scored", name[:30], total)
        time.sleep(4)
    res.sort(key=lambda r: -r["total"])
    lines = []
    for i, r in enumerate(res, 1):
        pt = r["parts"]
        lines.append(f"#{i} {r['name']} ({r['code']}) | mcap Rs {int(r['mcap']):,} Cr | SCORE {r['total']}/100")
        lines.append(f"   growth {pt['growth']}/25 | visibility {pt['visibility']}/25 | catalysts {pt['catalysts']}/25 | clarity {pt['clarity']}/15 | tone {pt['tone']}/10 | risks {pt['risk_penalty']}")
        lines.append(f"   facts verified in transcript: {r['verified']} of {r['claims']} claimed")
        lines.append(f"   story: {r['f'].get('one_line')}")
        for c in r["facts"]["catalysts"][:2]:
            lines.append(f"   + {c.get('detail')}")
        for k in r["facts"]["risks"][:2]:
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
