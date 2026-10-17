"""Evening recap of the day's major BSE announcements: AI-read impact score (-5..+5), one-line summaries, day tone.
Dry run / sample: python scripts/recap_post.py YYYY-MM-DD [send]  (send=1 posts to the Market group with a SAMPLE label)."""
import os, sys, re, json, time
from datetime import datetime, timedelta, timezone
import requests
sys.path.insert(0, os.path.dirname(__file__))
import news_posts as NP
import news_brief as NB
from ci_out import p, publish

IST = timezone(timedelta(hours=5, minutes=30))
OUT = os.environ.get("OUT_DIR", "out")
PROMPT = """You rate Indian stock-market exchange filings for a daily recap. For EACH item return a score and a one-line summary.
Return ONLY a JSON list: [{"i":<item number>,"s":<integer -5..5>,"t":"ONE short plain sentence, MAX 55 characters, WITHOUT the company name, e.g. \"Wins Rs 198 Cr order from State Bank of India\" - what happened and how much","k":"<=16 chars key figure exactly as in the text (e.g. Rs 198 Cr, AA+ from AA, 70% stake) or empty"}]
Score = likely impact on the company's shareholders, judged from the filing text only. Be selective and use the full range:
0 = routine/procedural (copies of orders, meeting adjournments, intimations); +-1 = minor; +-2 = noticeable; +-3 = meaningful (sizeable order, rating upgrade/downgrade by a notch, completed acquisition); +-4 = large; +-5 = rare and major (default, fraud, insolvency, rating to junk, very large order or merger vs company size).
Insolvency/NCLT proceedings against the company, creditors' committee meetings, lenders' defaults, NCLAT/court appeals by or against the company, regulatory or tax demands are NEGATIVE (-2 to -5), not 0. Rating upgrades are positive, downgrades negative; a dividend is +1 or +2; a resignation of a CFO/CEO is -1 or -2; order wins score by size.
Rules: the sentence must be complete and fit in 55 characters (rephrase to be shorter, never cut); use ONLY facts in the text; do not add numbers or opinions; keep numbers exactly as written; no advice or predictions.
Items:
@ITEMS"""

KW_POS = re.compile(r"upgrade|positive|approv|award|received order|secure|win|acquir|bonus|dividend|record|commission|launch|expan", re.I)
KW_NEG = re.compile(r"downgrad|default|fraud|insolv|cirp|penalt|regulatory action|resign|cessation|delist|negative|suspend|rejected", re.I)

def fetch_day(day):
    from bse import BSE
    rows, pg = [], 1
    with BSE(download_folder="./") as bse:
        while pg <= 80:
            d = bse.announcements(page_no=pg, from_date=day, to_date=day)
            t = d.get("Table", [])
            if not t:
                break
            rows += t
            if len(rows) >= (d.get("Table1") or [{}])[0].get("ROWCNT", 0):
                break
            pg += 1
    return rows

def detail_of(rec, allow_pdf):
    head = NP.title_of(rec)
    body = re.sub(r"\s+", " ", (rec.get("HEADLINE") or "").strip())
    more = re.sub(r"\s+", " ", (rec.get("MORE") or "").strip())
    d = (body if body.lower() not in head.lower() else "") or more
    d = d[:600]
    if (not d or len(d) < 70 or NP.GENERIC_RX.match(d)) and allow_pdf:
        ex = NP.pdf_excerpt(rec, 550)
        if ex:
            d = ex
    return head, d

def rule_score(tag, head, d):
    t = f"{head} {d}"
    s = {"ORDER WIN": 2, "ACQUISITION": 1, "CREDIT RATING": 0, "DIVIDEND": 1, "CORPORATE ACTION": 1, "MANAGEMENT": 0, "RISK": -3}.get(tag, 0)
    if KW_NEG.search(t): s -= 1
    if tag == "CREDIT RATING" and re.search(r"upgrad|positive", t, re.I): s += 2
    if tag == "CREDIT RATING" and re.search(r"downgrad|negative|default", t, re.I): s -= 3
    return max(-5, min(5, s))

def gemini_shorten(x, key):
    prompt = ("Rewrite as ONE complete plain sentence of MAX 45 characters, without the company name, keeping the key fact and number exactly as written. "
              "Return ONLY the sentence.\nSentence: " + x["line"] + "\nFiling text: " + x["detail"][:400])
    try:
        r = requests.post(f"{NB.BASE}/models/{NB.MODEL}:generateContent", headers={"x-goog-api-key": key}, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}, timeout=40)
        if r.status_code == 200:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"')
            if NB._ok({"headline": t, "bullets": ["x"]}, x["head"] + " " + x["detail"]):
                return t
    except Exception:
        pass
    return None

def gemini_score(batch, key):
    items = "\n".join(f"{n}. [{x['tag']}] {x['company']}: {x['head']} | {x['detail'][:420]}" for n, x in enumerate(batch, 1))
    body = {"contents": [{"parts": [{"text": PROMPT.replace("@ITEMS", items)}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for k in range(5):
        try:
            r = requests.post(f"{NB.BASE}/models/{NB.MODEL}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=60)
            if r.status_code == 200:
                txt = re.sub(r"^```json|```$", "", r.json()["candidates"][0]["content"]["parts"][0]["text"].strip())
                try:
                    out = json.loads(txt)
                except Exception:
                    out = [{"i": m.group(1), "s": m.group(2), "t": m.group(3), "k": m.group(4)} for m in re.finditer(
                        r'"i"\s*:\s*(\d+)\s*,\s*"s"\s*:\s*(-?\d+)\s*,\s*"t"\s*:\s*"(.*?)"\s*,\s*"k"\s*:\s*"(.*?)"\s*[,}]', txt, re.S)]
                    p("gemini json repaired:", len(out))
                return {int(o["i"]): o for o in out if isinstance(o, dict) and "i" in o and "s" in o}
            p("gemini HTTP", r.status_code)
        except Exception as e:
            p("gemini error", repr(e)[:80])
        time.sleep(6 * (k + 1))
    return {}


MONEY = re.compile(r"(?:Rs\.?|INR|\u20b9)\s*([\d,]+(?:\.\d+)?)(?:\s*(crores?|crs?\b|million|mn\b|billion|bn\b|lakhs?|lacs?)\b)?", re.I)

def _money(m):
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return m.group(0)
    u = (m.group(2) or "").lower()
    if u.startswith("cr"): c = v
    elif u.startswith(("mill", "mn")): c = v / 10
    elif u.startswith(("bill", "bn")): c = v * 100
    elif u.startswith(("lakh", "lac")): c = v / 100
    else: c = v / 1e7
    if c >= 0.995: return f"\u20b9{round(c):,} Cr"
    if c * 100 >= 0.995: return f"\u20b9{round(c * 100):,} lakh"
    return f"\u20b9{round(c * 1e7):,}"

def nodec(t):
    t = MONEY.sub(_money, t or "")
    return re.sub(r"(\d[\d,]*)\.\d+", lambda m: f"{round(float(m.group(0).replace(',', ''))):,}", t)

def strip_co(line, company):
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    cw = [x for x in company.split() if norm(x) not in ("ltd", "limited", "pvt", "private", "")]
    lw = line.strip().split()
    cut = 0
    for j in range(1, min(len(lw), 7) + 1):
        a = norm("".join(lw[:j]))
        if any(a == norm("".join(cw[:k])) for k in range(1, len(cw) + 1)):
            cut = j
    rest = lw[cut:]
    while rest and norm(rest[0]) in ("ltd", "limited", "has", "have", "had", "is", "was", "announced", "informed", "that", "the", "company", "pvt", "private"):
        rest = rest[1:]
    if rest and norm(rest[0]) in ("its", "companys"):
        rest = rest[1:]
    ln = " ".join(rest)
    return (ln[:1].upper() + ln[1:]) if ln else line

def synth(x):
    k = x.get("key") or ""
    return {"ORDER WIN": f"Order received: {k}" if k else "New order received", "ACQUISITION": "Acquisition / scheme announced", "CREDIT RATING": "Credit rating action", "RISK": "Risk event disclosed"}.get(x["tag"], x["head"][:50])

def build(day, max_items=80):
    rows = fetch_day(day)
    cands, tagcount = [], {}
    for r in rows:
        tag = NP.classify(r)
        if tag:
            cands.append((tag, r))
    p(f"announcements {len(rows)}, candidates {len(cands)}")
    pri = {"RISK": 0, "ACQUISITION": 1, "ORDER WIN": 2, "CREDIT RATING": 3, "CORPORATE ACTION": 4, "DIVIDEND": 5, "MANAGEMENT": 6}
    cands.sort(key=lambda c: (pri.get(c[0], 9), -len(c[1].get("HEADLINE") or "")))
    cands = cands[:max_items]
    items, pdfs = [], 0
    for tag, r in cands:
        head, d = detail_of(r, allow_pdf=pdfs < 25)
        if d and not (r.get("HEADLINE") or "").strip() and len(d) > 0:
            pdfs += 1
        items.append({"tag": tag, "company": NP.company_of(r)[:44], "code": r.get("SCRIP_CD"), "head": head, "detail": d or head, "url": NP.link(r), "id": r["NEWSID"]})
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    scored = 0
    for i in range(0, len(items), 15):
        batch = items[i:i + 15]
        res = gemini_score(batch, key) if key else {}
        if key and len(res) < len(batch):
            miss = [n for n in range(1, len(batch) + 1) if n not in res]
            for h in range(0, len(miss), 5):
                sub = [batch[n - 1] for n in miss[h:h + 5]]
                r2 = gemini_score(sub, key)
                for j, n in enumerate(miss[h:h + 5], 1):
                    if j in r2:
                        res[n] = r2[j]
        for n, x in enumerate(batch, 1):
            o = res.get(n)
            src = f"{x['head']} {x['detail']}"
            if o and isinstance(o.get("s"), (int, float)) and o.get("t") and NB._ok({"headline": o["t"], "sub": str(o.get("k") or ""), "bullets": ["x"]}, src):
                x["score"], x["line"], x["how"] = int(max(-5, min(5, round(o["s"])))), str(o["t"]).strip(), "ai"
                x["key"] = str(o.get("k") or "").strip()[:24]
                scored += 1
            else:
                x["score"], x["how"] = rule_score(x["tag"], x["head"], x["detail"]), "rule"
                gen = re.search(r"receipt of order|award of order|^acquisition$|^intimation|^announcement", x["head"], re.I) or len(x["head"]) < 25
                x["line"] = (x["detail"] if gen and len(x["detail"]) > 30 else x["head"])[:90]
    p(f"scored by AI {scored}/{len(items)}")
    import cards_recap as CR
    short = 0
    for x in items:
        x["key"] = nodec(x.get("key") or "")
        if x["key"] and not re.search(r"\u20b9|%|\bCr\b|lakh|stake|equity|\b[A-D]{1,3}[+-]|crore", x["key"], re.I):
            x["key"] = ""
        if x["tag"] == "ORDER WIN" and x["score"] < 0:
            x["tag"] = "RISK"
        ln = nodec(strip_co(x["line"], x["company"]))
        if not CR.fits(ln):
            short += 1
            ln2 = None
            if key and x.get("how") == "ai":
                r = gemini_shorten(x, key)
                ln2 = nodec(strip_co(r, x["company"])) if r else None
            ln = ln2 if ln2 and CR.fits(ln2) else synth(x)
        x["line"] = ln
    p(f"lines needing shortening: {short}")
    # one entry per company (strongest), remember how many filings
    best = {}
    for x in items:
        c = best.get(x["company"])
        if c is None or abs(x["score"]) > abs(c["score"]):
            x["n"] = (c["n"] if c else 0) + 1
            best[x["company"]] = x
        else:
            c["n"] = c.get("n", 1) + 1
    each = [c for c in best.values() if c["tag"] in ("ORDER WIN", "ACQUISITION") or abs(c["score"]) >= 3]
    p(f"kept {len(each)} of {len(best)} companies (orders, deals, and big rating/risk moves)")
    for x in each:
        x.setdefault("key", "")
    def crv(x):
        m = re.search(r"\u20b9([\d,]+)\s*(Cr|lakh)", x.get("key") or "")
        if not m:
            return 0.0
        v = float(m.group(1).replace(",", ""))
        return v if m.group(2) == "Cr" else v / 100
    for x in each:
        x["val"] = crv(x)
    pos = sorted([x for x in each if x["score"] > 0], key=lambda x: (-x["score"], -x["val"], x["company"]))
    neg = sorted([x for x in each if x["score"] < 0], key=lambda x: x["score"])
    neu = [x for x in each if x["score"] == 0]
    mix = {}
    for x in items:
        mix[x["tag"]] = mix.get(x["tag"], 0) + 1
    fii = None
    try:
        import market_posts as mpx
        f = mpx.fetch_fii_dii()
        fii = {"date": f["date"].strftime("%d %b"), "fii": f["fii"]["net"], "dii": f["dii"]["net"]}
    except Exception as e:
        p("fii/dii unavailable:", repr(e)[:80])
    cnt = {"orders": sum(1 for x in each if x["tag"] == "ORDER WIN"), "deals": sum(1 for x in each if x["tag"] == "ACQUISITION"), "alerts": sum(1 for x in each if x["tag"] not in ("ORDER WIN", "ACQUISITION"))}
    return {"fii": fii, "cnt": cnt, "date": day.strftime("%d %b %Y"), "scanned": len(rows), "notable": len(each), "pos": pos, "neg": neg, "neu": len(neu), "neu_items": neu, "mix": mix,
            "ai": scored >= len(items) * 0.5}

def tag_friend(first, token, chat):
    """Tag a group member (needs an admin entry or a known user id); falls back to the plain name. Never prints ids."""
    api = f"https://api.telegram.org/bot{token}"
    ent, uid = [], None
    try:
        for a in requests.get(api + "/getChatAdministrators", params={"chat_id": chat}, timeout=20).json().get("result", []):
            u = a.get("user", {})
            if u.get("first_name", "").lower().startswith(first.lower()):
                uid = u["id"]
    except Exception:
        pass
    text = f"{first} - sample recap card above, please look and share feedback: layout, wording, what to add or remove."
    if uid:
        ent = [{"type": "text_mention", "offset": 0, "length": len(first), "user": {"id": uid}}]
    r = requests.post(api + "/sendMessage", data={"chat_id": chat, "text": text, **({"entities": json.dumps(ent)} if ent else {})}, timeout=30)
    p("tag message sent:", r.json().get("ok"), "(real tag)" if uid else "(plain name; no user id known)")

def main():
    day = datetime.strptime(sys.argv[1], "%Y-%m-%d") if len(sys.argv) > 1 else datetime.now(IST).replace(tzinfo=None)
    send = len(sys.argv) > 2 and sys.argv[2] == "1"
    d = build(day)
    import cards_recap as CR
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"recap_{day:%Y%m%d}.png")
    CR.render_recap(d, path)
    p("card:", path, "pos", len(d["pos"]), "neg", len(d["neg"]), "neu", d["neu"])
    if send:
        import market_posts as mp
        mp.SEND = True
        cap = f"SAMPLE - evening filings recap built from real BSE filings of {d['date']} (AI-read scores; format under review).\nFor educational purpose only."
        ok = mp.post([(path, cap, None)])
        p("sent:", ok)
        if ok:
            tag_friend("Abhimanyu", mp.TOKEN, mp.CHAT)
    publish()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        p("ERROR", traceback.format_exc()[-900:])
        publish()
