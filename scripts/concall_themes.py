"""Dry run: Concall Mentions Index. Counts how often themes (data centres, China, pricing pressure ...) come up in official earnings-call transcripts
filed on BSE, for the current results season versus the same days one quarter ago (91 days earlier) and one year ago (364 days earlier).
Free: no Gemini, plain pattern counting. Posts nothing. Stores per-transcript counts in store/concall_themes/<YYYY-MM>.jsonl (not the full text for old seasons).
Counts show how often a topic is discussed, NOT whether the tone is good or bad."""
import os, sys, re, io, json, gzip, glob, traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import recap_post as rp
import news_posts as NP
import store

_IST = datetime.utcnow() + timedelta(hours=5, minutes=30)
CUR0 = os.environ.get("CUR_FROM", "").strip() or "2026-10-06"
CUR1 = os.environ.get("CUR_TO", "").strip() or _IST.strftime("%Y-%m-%d")
MIN_WORDS = 1500

def _t(pat):
    return re.compile(pat, re.I)

THEMES = {
    "AI / data centres": _t(r"\bdata ?cent(?:er|re)s?\b|hyperscal\w*|\bgen(?:erative)? ?ai\b|artificial intelligence|\bai\b|\bllms?\b"),
    "GPUs / semiconductors": _t(r"\bgpus?\b|semiconductors?|\bfabs?\b"),
    "Cooling / HVAC": _t(r"\bcooling\b|\bhvac\b|\bchillers?\b"),
    "Power / grid / transformers": _t(r"power demand|electricity demand|\bgrid\b|transformers?\b|transmission (?:line|capex|project)"),
    "Cables and wires": _t(r"\bcables?\b|\bwires?\b"),
    "Solar / renewables / storage": _t(r"\bsolar\b|renewables?|wind (?:energy|power)|green hydrogen|\bbess\b|battery storage"),
    "EV / batteries": _t(r"\bevs?\b|electric vehicles?|lithium|batter(?:y|ies)"),
    "Defence / aerospace": _t(r"\bdefen[cs]e\b|aerospace|\bdrdo\b"),
    "Railways": _t(r"\brailways?\b|vande bharat"),
    "Capex / capacity expansion": _t(r"\bcapex\b|capital expenditure|capacity expansion|greenfield|brownfield"),
    "Order book / inflow": _t(r"order ?book|order inflows?|order pipeline"),
    "Pricing pressure": _t(r"pric(?:e|ing) (?:pressure|competition|war|cuts?|erosion)|realisation (?:pressure|decline|drop)"),
    "Price hikes / pricing power": _t(r"price (?:hikes?|increases?)|pricing power|took (?:a )?price"),
    "Input cost inflation": _t(r"raw material (?:cost|price|inflation)|input cost|commodity (?:price|inflation)|\bfreight\b"),
    "Margin expansion": _t(r"margin (?:expansion|improvement)|operating leverage"),
    "Margin pressure": _t(r"margin (?:pressure|contraction|compression|dilution|decline)"),
    "Weak demand": _t(r"(?:weak|soft|muted|subdued|slow\w*) (?:demand|consumption)|demand (?:slowdown|weakness|headwinds?)"),
    "Demand recovery": _t(r"(?:demand|consumption) (?:recover\w*|revival|pick[- ]?up|improv\w*)|green shoots"),
    "Rural": _t(r"\brural\b"),
    "Festive season": _t(r"\bfestive\b|\bdiwali\b|\bnavratri\b"),
    "Monsoon / weather": _t(r"\bmonsoon\b|rainfall|unseasonal"),
    "US tariffs": _t(r"\btariffs?\b"),
    "China": _t(r"\bchina\b|\bchinese\b"),
    "Exports": _t(r"\bexports?\b"),
    "Supply chain": _t(r"supply chains?"),
    "Working-capital stress": _t(r"working capital (?:stress|pressure|intensive)|receivable days|debtor days|collections? (?:delay|stress|pressure)"),
    "Debt reduction": _t(r"debt (?:reduction|repayment|free)|deleverag\w*|net debt"),
    "Fund raise": _t(r"fund ?raise|\bqip\b|preferential (?:issue|allotment)|rights issue|\bwarrants?\b"),
    "Acquisitions / M&A": _t(r"\bacqui(?:re|red|sitions?)\b|\bm&a\b|\bmergers?\b|amalgamation"),
    "Asset quality / credit cost": _t(r"credit cost|\bgnpa?\b|asset quality|\bnpas?\b|slippages?"),
    "Interest rates": _t(r"rate cuts?|repo rate|interest rates?|cost of (?:funds|borrowing)"),
    "Real estate / housing": _t(r"real estate|housing demand|pre-?sales"),
    "Attrition / wages": _t(r"attrition|wage (?:hikes?|inflation)|\bheadcount\b"),
    "GST / PLI / policy": _t(r"\bgst\b|\bpli\b|anti-?dumping"),
    "Guidance": _t(r"\bguidance\b"),
    "Premiumisation": _t(r"premiumi[sz]ation|premium (?:products|portfolio|mix)"),
    "US FDA / generics": _t(r"\bus ?fda\b|\busfda\b|\bgenerics?\b|\bandas?\b"),
    "Metal / crude prices": _t(r"(?:steel|copper|aluminium|zinc|crude|oil) prices?"),
    "Quick commerce": _t(r"quick commerce|q-?commerce|\bblinkit\b|\bzepto\b|\binstamart\b"),
}

def analyze(text, snip=False):
    t = re.sub(r"\s+", " ", text)
    words = len(t.split())
    c, s = {}, {}
    for k, rx in THEMES.items():
        ms = list(rx.finditer(t))
        if ms:
            c[k] = len(ms)
            if snip:
                m = ms[0]
                s[k] = t[max(0, m.start() - 110): min(len(t), m.end() + 110)]
    return words, c, s

def pdf_text(url):
    from pypdf import PdfReader
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    if r.status_code != 200 or len(r.content) > 12_000_000:
        return None
    rd = PdfReader(io.BytesIO(r.content))
    return " ".join((pg.extract_text() or "") for pg in rd.pages)

def find(d0, d1):
    rows = []
    d = datetime.fromisoformat(d0); end = datetime.fromisoformat(d1)
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
                p("fetch err", d.date(), repr(e)[:60])
        d += timedelta(days=1)
    seen, out = set(), []
    for x in rows:
        k = (str(x.get("SCRIP_CD")).strip(), (x.get("NEWS_DT") or "")[:10])
        if k not in seen:
            seen.add(k); out.append(x)
    return out

def load_text(code, day, x):
    f = os.path.join(store.ROOT, "concall_text", f"{code}_{day}.txt.gz")
    if os.path.exists(f):
        return gzip.open(f, "rt", errors="ignore").read()
    return pdf_text(NP.link(x))

def one(job):
    x, keep_snip = job
    code = str(x.get("SCRIP_CD")).strip(); day = (x.get("NEWS_DT") or "")[:10]
    try:
        txt = load_text(code, day, x)
        if not txt:
            return None
        words, c, s = analyze(txt, snip=keep_snip)
        if words < MIN_WORDS:
            return {"key": f"{code}|{day}", "code": code, "name": (x.get("SLONGNAME") or "").strip(), "day": day, "words": words, "c": {}, "skip": "short"}
        rec = {"key": f"{code}|{day}", "code": code, "name": (x.get("SLONGNAME") or "").strip(), "day": day, "words": words, "c": c}
        if keep_snip:
            rec["s"] = s
        return rec
    except Exception:
        return None

def load_all():
    out = {}
    for f in glob.glob(os.path.join(store.ROOT, "concall_themes", "*.jsonl")):
        for ln in open(f, encoding="utf-8"):
            try:
                r = json.loads(ln); out[r["key"]] = r
            except Exception:
                pass
    return out

def save_all(recs):
    d = os.path.join(store.ROOT, "concall_themes"); os.makedirs(d, exist_ok=True)
    by = {}
    for r in recs.values():
        by.setdefault((r.get("day") or "0000-00")[:7], []).append(r)
    for m, rows in by.items():
        rows.sort(key=lambda r: (r.get("day") or "", r.get("code") or ""))
        with open(os.path.join(d, f"{m}.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

def shift(day, n):
    return (datetime.fromisoformat(day) - timedelta(days=n)).strftime("%Y-%m-%d")

def window(recs, a, b):
    return [r for r in recs.values() if a <= (r.get("day") or "") <= b and r.get("words", 0) >= MIN_WORDS]

def stats(rs):
    tw = sum(r["words"] for r in rs) or 1
    out = {}
    for k in THEMES:
        n = sum(1 for r in rs if r["c"].get(k))
        m = sum(r["c"].get(k, 0) for r in rs)
        out[k] = {"n": n, "pct": 100.0 * n / max(1, len(rs)), "per100k": m * 1e5 / tw, "m": m}
    return out

def main():
    wins = {"CUR": (CUR0, CUR1), "PREV": (shift(CUR0, 91), shift(CUR1, 91)), "YOY": (shift(CUR0, 364), shift(CUR1, 364))}
    recs = load_all()
    p("windows:", wins, "| stored transcripts before run:", len(recs))
    for name, (a, b) in wins.items():
        rows = find(a, b)
        todo = [(x, name == "CUR") for x in rows if f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}" not in recs or (name == "CUR" and "s" not in recs.get(f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}", {}) and not recs.get(f"{str(x.get('SCRIP_CD')).strip()}|{(x.get('NEWS_DT') or '')[:10]}", {}).get("skip"))]
        p(name, a, "to", b, "| transcript filings found:", len(rows), "| to analyse:", len(todo))
        with ThreadPoolExecutor(6) as ex:
            got = [r for r in ex.map(one, todo) if r]
        for r in got:
            recs[r["key"]] = r
        p(name, "analysed now:", len(got))
    save_all(recs)
    W = {n: window(recs, a, b) for n, (a, b) in wins.items()}
    S = {n: stats(rs) for n, rs in W.items()}
    for n, rs in W.items():
        p(f"{n}: {len(rs)} transcripts with text, {sum(r['words'] for r in rs):,} words")
    cur, prev, yoy = S["CUR"], S["PREV"], S["YOY"]
    nc, np_, ny = len(W["CUR"]), len(W["PREV"]), len(W["YOY"])
    if nc < 10:
        p("Too few current transcripts for a fair read."); return
    p("")
    p("THEME | % of calls mentioning: now / qtr ago / yr ago | mentions per 100k words now | x vs qtr | x vs yr")
    order = sorted(THEMES, key=lambda k: -cur[k]["pct"])
    rows_out = []
    for k in order:
        a, b, c = cur[k], prev[k], yoy[k]
        xq = (a["per100k"] / b["per100k"]) if b["per100k"] > 0 else None
        xy = (a["per100k"] / c["per100k"]) if c["per100k"] > 0 else None
        rows_out.append({"theme": k, "now_pct": round(a["pct"], 1), "q_pct": round(b["pct"], 1) if np_ else None, "y_pct": round(c["pct"], 1) if ny else None,
                         "now_per100k": round(a["per100k"], 1), "x_q": round(xq, 2) if xq else None, "x_y": round(xy, 2) if xy else None, "n_now": a["n"]})
        p(f"{k} | {a['pct']:.0f}% / {b['pct']:.0f}% / {c['pct']:.0f}% | {a['per100k']:.1f} | {('%.1fx' % xq) if xq else 'new' if a['per100k']>0 else '-'} | {('%.1fx' % xy) if xy else 'new' if a['per100k']>0 else '-'}")
    p("")
    p("RISERS (at least 4 calls now, mentions per 100k words up 1.5x or more vs a quarter ago):")
    risers = [r for r in rows_out if r["n_now"] >= 4 and (r["x_q"] is None and r["now_per100k"] > 0 or (r["x_q"] and r["x_q"] >= 1.5))]
    risers.sort(key=lambda r: -(r["x_q"] or 9.99))
    for r in risers[:8]:
        k = r["theme"]
        top = sorted(W["CUR"], key=lambda z: -z["c"].get(k, 0))[:3]
        p(f"* {k}: {r['now_pct']}% of calls now vs {r['q_pct']}% a quarter ago; top: " + ", ".join(f"{z['name']} ({z['c'].get(k,0)}x)" for z in top))
        z = top[0]
        sn = (z.get("s") or {}).get(k)
        if sn:
            p(f'    e.g. {z["name"]}: "...{sn}..."')
    p("")
    p("FALLERS (at least 4 calls a quarter ago, down to 0.6x or less):")
    fall = [r for r in rows_out if r["x_q"] and r["x_q"] <= 0.6 and prev[r["theme"]]["n"] >= 4]
    for r in sorted(fall, key=lambda r: r["x_q"])[:6]:
        p(f"* {r['theme']}: {r['now_pct']}% now vs {r['q_pct']}% a quarter ago ({r['x_q']}x)")
    p("")
    p("CAVEATS: counts show how often a topic is discussed, not tone. Early-season calls are not the same company mix as a quarter or year ago. Image-only or short PDFs are skipped.")
    os.makedirs("out", exist_ok=True)
    json.dump({"windows": wins, "n": {k: len(v) for k, v in W.items()}, "rows": rows_out}, open("out/concall_index.json", "w"))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        p("ERR", traceback.format_exc()[-1500:])
    publish()
