"""Market news poster (everything market-related EXCEPT results): BSE announcements by curated category (+ RBI/SEBI feeds).
Used inside the poll loop via tick(bse); also runnable as a dry run: python scripts/news_posts.py dry
Text on the card is as filed (BSE headline/subject) - no summaries are written."""
import os, re, sys, json, time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p
import cards_market as CM
import tags

IST = timezone(timedelta(hours=5, minutes=30))
STATE = "state/news_state.json"
OUT = os.environ.get("OUT_DIR", "out")
SEND = os.environ.get("POST_SEND", "0") == "1"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("MARKET_CHAT_ID", "").strip()
MAX_AGE_H = 3          # never post an item older than this (e.g. after a long outage)
MAX_PER_TICK = 8       # flood guard per check
DISC = "For educational purpose only."

CONCALL_RX = re.compile(r"conference call|earnings call|con-?call|concall|analyst call|investor call", re.I)
MGMT_RX = re.compile(r"chief financial officer|\bcfo\b|chief executive|\bceo\b|managing director|\bmd\b|chairman|chief operating|\bcoo\b|whole[- ]time director", re.I)

def sub_of(rec):
    return (rec.get("SUBCATNAME") or "").strip()

def title_of(rec):
    t = (rec.get("NEWSSUB") or "").strip()
    m = re.match(r"^(.*?)\s*-\s*\d{5,6}\s*-\s*(.*)$", t)
    t = (m.group(2) if m else t).strip()
    t = re.sub(r"^Announcement under Regulation 30 \(LODR\)\s*-\s*", "", t, flags=re.I)
    t = re.sub(r"^Corporate Action\s*-\s*", "", t, flags=re.I)
    return t.replace("_", " ").replace("  ", " ").strip()

def classify(rec):
    """Return a card tag, or None if this announcement is not newsworthy enough."""
    cat = (rec.get("CATEGORYNAME") or "").strip().lower()
    if cat in ("result", "board meeting", "agm/egm", "insider trading / sast", "new listing"):
        return None
    sub = sub_of(rec).lower()
    text = f"{rec.get('NEWSSUB') or ''} {rec.get('HEADLINE') or ''}"
    if "award of order" in sub or "receipt of order" in sub:
        return "ORDER WIN"
    if any(k in sub for k in ("acquisition", "scheme of arrangement", "open offer", "amalgamation", "merger", "demerger", "takeover", "divestment", "slump sale")):
        return "ACQUISITION"
    if "credit rating" in sub:
        return "CREDIT RATING"
    if sub in ("dividend", "dividend updates"):
        return "DIVIDEND"
    if any(k in sub for k in ("bonus", "split", "sub-division", "post buyback", "buy back of equity", "buyback", "rights issue", "record date",
                              "qualified institutional", "preferential issue", "raising of funds", "delisting", "fund raising")) and "daily buy back" not in sub:
        return "CORPORATE ACTION"
    if any(k in sub for k in ("insolvency", "cirp", "default", "fraud", "action(s) initiated", "regulatory action")):
        return "RISK"
    if MGMT_RX.search(sub) or (sub in ("change in management", "change in directorate", "cessation", "resignation of director") and MGMT_RX.search(text)):
        return "MANAGEMENT"
    return None

def company_of(rec):
    return (rec.get("SLONGNAME") or "").strip() or (re.match(r"^(.*?)\s*-\s*\d{5,6}", rec.get("NEWSSUB") or "") or [None, "Company"])[1]

def link(rec):
    a = rec.get("ATTACHMENTNAME")
    return f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{a}" if a else (rec.get("NSURL") or "")

def parse_dt(rec):
    try:
        return datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19]).replace(tzinfo=IST)
    except Exception:
        return None

GENERIC_RX = re.compile(r"^(as enclosed|please find( the)? enclosed|enclosed|intimation|please find attached|attached|kindly find|as attached|pursuant to)", re.I)

def pdf_excerpt(rec, limit=650):
    """First meaningful text of the filing PDF (as filed, no rewriting). None if unreadable/scanned."""
    import requests, io
    url = link(rec)
    if not url.lower().endswith(".pdf"):
        return None
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if r.status_code != 200 or len(r.content) > 6_000_000:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(r.content))
        txt = " ".join((rd.pages[i].extract_text() or "") for i in range(min(2, len(rd.pages))))
    except Exception:
        return None
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) < 80:
        return None
    m = re.search(r"\b(sub(ject)?|re|ref)\s*[:\-\.]\s*", txt, re.I)
    if m and m.start() < len(txt) * 0.6:
        txt = txt[m.start():]
    else:
        txt = re.sub(r"^(to,?\s*)?(the\s+)?(manager|secretary|general manager|listing)[^.]{0,200}?(mumbai|exchange|limited)[^.]{0,120}?(dear sir[^,.]*[,.]?|sir[^,.]*[,.])?\s*", "", txt, count=1, flags=re.I)
    return txt[:limit].rstrip() + ("..." if len(txt) > limit else "")

def build_card(rec, tag):
    dt = parse_dt(rec)
    when = dt.strftime("%d %b %Y, %H:%M IST") if dt else ""
    head = title_of(rec)
    body = re.sub(r"\s+", " ", (rec.get("HEADLINE") or "").strip())
    if body.lower() == head.lower() or body.lower() in head.lower():
        body = ""
    more = re.sub(r"\s+", " ", (rec.get("MORE") or "").strip())
    detail = (body or more)[:700] or None
    if not detail or len(detail) < 70 or GENERIC_RX.match(detail):
        ex = pdf_excerpt(rec)
        if ex:
            detail = ex
    import news_brief
    br, how = news_brief.brief(tag, company_of(rec)[:48], head, detail)
    p("   brief via", how)
    head = br.get("headline") or head
    it = {"tag": tag, "company": company_of(rec)[:48], "meta": f"BSE {rec.get('SCRIP_CD')}  |  {when}", "headline": head, "sub": br.get("sub"), "bullets": br.get("bullets") or [], "detail": None if br.get("bullets") else detail, "source": "BSE announcement"}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"news_{rec['NEWSID']}.png")
    CM.render_news(it, path)
    cap = f"{tag.title()}: {it['company']} (BSE {rec.get('SCRIP_CD')})\n{head}\nFiling: {link(rec)}\n\n{DISC}"
    topic = {"ORDER WIN": "#OrderWin", "ACQUISITION": "#Acquisition", "CREDIT RATING": "#CreditRating", "DIVIDEND": "#Dividend", "CORPORATE ACTION": "#CorporateAction", "MANAGEMENT": "#Management", "RISK": "#StockMarketIndia"}.get(tag, "#StockMarketIndia")
    tw = f"{tag.title()}: {it['company']} - {head}"[:215] + "\n" + tags.join(tags.company_tag(code=rec.get("SCRIP_CD"), name=it["company"]), topic)
    return path, cap, tw

# ------------------------------------------------------------------ state / telegram
def jload():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"ids": [], "init": False}

def jsave(st):
    st["ids"] = st["ids"][-4000:]
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"))

def send_photo(path, cap, tweet=None):
    import requests, xbuttons
    cap, flink = xbuttons.split_link(cap)
    data = {"chat_id": CHAT, "caption": cap[:1024]}
    if tweet:
        data["reply_markup"] = xbuttons.markup(tweet, flink)
    with open(path, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data=data, files={"photo": fh}, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False}

def fetch_today(bse, seen):
    rows, pg, total = [], 1, 0
    now = datetime.now(IST).replace(tzinfo=None)
    while pg <= 40:
        data = bse.announcements(page_no=pg, from_date=now, to_date=now)
        t = data.get("Table", [])
        if not t:
            break
        rows += t
        total += len(t)
        if any(r["NEWSID"] in seen for r in t):
            break
        if total >= (data.get("Table1") or [{}])[0].get("ROWCNT", 0):
            break
        pg += 1
    return rows

SEBI_ALLOW = re.compile(r"circular|consultation paper|framework|regulations|amendment|board meeting|guidelines|master circular|interim order|discussion paper|norms|margin|f&o|derivative|mutual fund|ipo|disclosure", re.I)
SEBI_DENY = re.compile(r"recovery certificate|remittance|exemption order|attachment|adjudication order|settlement order|in the matter of|appeal|corrigendum|tender|empanelment|vacancy|recruitment", re.I)

def sebi_ok(title):
    return bool(SEBI_ALLOW.search(title)) and not SEBI_DENY.search(title)

RSS = (("RBI", "https://www.rbi.org.in/pressreleases_rss.xml", re.compile(r"auction|treasury bill|ways and means|money market operation|state development loan|indicative calendar|weekly statistical|result of", re.I)),
       ("SEBI", "https://www.sebi.gov.in/sebirss.xml", None))

def fetch_rss(tag, url, skip_rx):
    import requests
    import xml.etree.ElementTree as ET
    from html import unescape
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    root = ET.fromstring(r.content.decode("utf-8-sig", "ignore").encode("utf-8"))
    out = []
    for it in root.iter("item"):
        title = re.sub(r"\s+", " ", unescape((it.findtext("title") or "").strip()))
        if not title or (skip_rx and skip_rx.search(title)) or (tag == "SEBI" and not sebi_ok(title)):
            continue
        desc = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or ""))).strip()
        out.append({"id": f"{tag}:{it.findtext('guid') or it.findtext('link') or title}", "tag": tag, "title": title, "link": it.findtext("link") or "", "desc": desc if desc.lower() != title.lower() else "", "date": (it.findtext("pubDate") or "").strip()})
    return out

def build_rss_card(x):
    os.makedirs(OUT, exist_ok=True)
    org = "Reserve Bank of India" if x["tag"] == "RBI" else "SEBI"
    it = {"tag": x["tag"], "company": org, "meta": f"Press release  |  {x['date']}"[:90], "headline": x["title"], "detail": (x["desc"] or None) and x["desc"][:650], "source": f"{org} website"}
    path = os.path.join(OUT, f"news_{abs(hash(x['id']))}.png")
    CM.render_news(it, path)
    return path, f"{x['tag']}: {x['title']}\n{x['link']}\n\nFor educational purpose only.", f"{x['tag']}: {x['title']}"[:230] + "\n#" + x["tag"] + " #StockMarketIndia"

_last = [0.0]
_last_rss = [0.0]

def _bse_tick(bse):
    if not (SEND and CHAT):
        return False, []
    if time.time() - _last[0] < 20:
        return False, []
    _last[0] = time.time()
    st = jload()
    seen = set(st["ids"])
    rows = [r for r in fetch_today(bse, seen) if r["NEWSID"] not in seen]
    lines, changed = [], False
    if not rows:
        return False, lines
    if not st.get("init"):
        st["ids"] += [r["NEWSID"] for r in rows]       # first ever run: baseline only, post nothing old
        st["init"] = True
        jsave(st)
        return True, ["news baseline set: %d announcements marked seen" % len(rows)]
    rows.sort(key=lambda r: r.get("NEWS_DT") or "")
    now = datetime.now(IST)
    posted = 0
    for r in rows:
        tag = classify(r)
        dt = parse_dt(r)
        fresh = dt is not None and now - dt <= timedelta(hours=MAX_AGE_H)
        if tag and fresh and posted < MAX_PER_TICK:
            try:
                path, cap, tw = build_card(r, tag)
                res = send_photo(path, cap, tw)
            except Exception as e:
                lines.append(f"news card error {r['NEWSID']}: {repr(e)[:120]}")
                res = {"ok": False}
            if not res.get("ok"):
                lines.append(f"news send failed {r['NEWSID']}: {str(res.get('description'))[:80]}")
                continue        # not marked seen -> retried next tick
            posted += 1
            lines.append(f"news posted {tag} {company_of(r)[:30]}")
            time.sleep(3.2)
        elif tag and fresh:
            continue            # over the per-tick cap: leave unseen, goes out next tick
        st["ids"].append(r["NEWSID"])
        changed = True
    if changed:
        jsave(st)
    return changed, lines


def _rss_tick():
    if time.time() - _last_rss[0] < 60:
        return False, []
    _last_rss[0] = time.time()
    st = jload()
    seen = set(st["ids"])
    lines, changed, posted = [], False, 0
    for tag, url, rx in RSS:
        try:
            items = [x for x in fetch_rss(tag, url, rx) if x["id"] not in seen]
        except Exception as e:
            lines.append(f"{tag} feed error: {repr(e)[:100]}")
            continue
        if not items:
            continue
        if not st.get(f"init_{tag}"):
            st["ids"] += [x["id"] for x in items]
            st[f"init_{tag}"] = True
            changed = True
            lines.append(f"{tag} baseline set ({len(items)})")
            continue
        for x in reversed(items):          # feeds list newest first
            if posted >= 4:
                break
            try:
                path, cap, tw = build_rss_card(x)
                res = send_photo(path, cap, tw)
            except Exception as e:
                lines.append(f"{tag} card error: {repr(e)[:100]}")
                continue
            if not res.get("ok"):
                lines.append(f"{tag} send failed: {str(res.get('description'))[:80]}")
                continue
            st["ids"].append(x["id"])
            changed = True
            posted += 1
            lines.append(f"news posted {tag}: {x['title'][:50]}")
            time.sleep(3.2)
    if changed:
        jsave(st)
    return changed, lines

def tick(bse):
    """Called by the poll loop (live only). Returns (changed, lines). Off unless NEWS_LIVE=1 (switched on only after Mayank approves the dry run)."""
    if not (SEND and CHAT) or os.environ.get("NEWS_LIVE", "0") != "1":
        return False, []
    a, la = False, []
    try:
        a, la = _bse_tick(bse)
    except Exception as e:
        la = [f"news bse error: {repr(e)[:150]}"]
    b, lb = False, []
    try:
        b, lb = _rss_tick()
    except Exception as e:
        lb = [f"news rss error: {repr(e)[:150]}"]
    return a or b, la + lb

def send_text(txt):
    import requests
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT, "text": txt}, timeout=30)
    return r.json()

def preview(day=None, per_tag=2, send=False):
    """Dry run: render sample cards (real filings of a past day) into OUT_DIR. No sending, no state."""
    from bse import BSE
    day = day or datetime.now(IST).replace(tzinfo=None)
    rows, pg = [], 1
    with BSE(download_folder="./") as bse:
        while pg <= 60:
            d = bse.announcements(page_no=pg, from_date=day, to_date=day)
            t = d.get("Table", [])
            if not t:
                break
            rows += t
            if len(rows) >= (d.get("Table1") or [{}])[0].get("ROWCNT", 0):
                break
            pg += 1
    if send and TOKEN and CHAT:
        send_text(f"TEST BATCH - new portrait news cards (bullet summaries) built from real filings of {day:%d %b %Y}. Please share feedback: is the text readable on your phone, what is useful, what is noise?")
    by = {}
    for r in rows:
        tg = classify(r)
        if tg:
            by.setdefault(tg, []).append(r)
    for tg, v in by.items():
        v.sort(key=lambda r: -len(r.get("HEADLINE") or ""))
        for r in v[:per_tag]:
            path, cap, tw = build_card(r, tg)
            p("card", tg, company_of(r), "->", path)
            if send and TOKEN and CHAT:
                p("   sent:", send_photo(path, cap, tw).get("ok")); time.sleep(3.2)
    for tag, url, rx in RSS:
        try:
            for x in fetch_rss(tag, url, rx)[:2]:
                path, cap, tw = build_rss_card(x)
                p("card", tag, x["title"][:60], "->", path)
                if send and TOKEN and CHAT:
                    p("   sent:", send_photo(path, cap, tw).get("ok")); time.sleep(3.2)
        except Exception as e:
            p(tag, "feed error", repr(e)[:100])

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "preview":
    from ci_out import publish
    d = datetime.strptime(sys.argv[2], "%Y-%m-%d") if len(sys.argv) > 2 else None
    try:
        preview(d, per_tag=int(os.environ.get("NEWS_PER_TAG", "2")), send=os.environ.get("NEWS_TEST_SEND", "0") == "1")
    except Exception:
        import traceback
        p("ERROR", traceback.format_exc()[-900:])
    publish()
