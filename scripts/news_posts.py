"""Market news poster (everything market-related EXCEPT results): BSE announcements by curated category (+ RBI/SEBI feeds).
Used inside the poll loop via tick(bse); also runnable as a dry run: python scripts/news_posts.py dry
Text on the card is as filed (BSE headline/subject) - no summaries are written."""
import os, re, sys, json, time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p
import cards_market as CM

IST = timezone(timedelta(hours=5, minutes=30))
STATE = "state/news_state.json"
OUT = os.environ.get("OUT_DIR", "out")
SEND = os.environ.get("POST_SEND", "0") == "1"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("MARKET_CHAT_ID", "").strip()
MAX_AGE_H = 3          # never post an item older than this (e.g. after a long outage)
MAX_PER_TICK = 8       # flood guard per check
DISC = "Source: BSE filings. Text as filed - read the full filing. Not investment advice."

CONCALL_RX = re.compile(r"conference call|earnings call|con-?call|concall|analyst call|investor call", re.I)
MGMT_RX = re.compile(r"chief financial officer|\bcfo\b|chief executive|\bceo\b|managing director|\bmd\b|chairman|chief operating|\bcoo\b|whole[- ]time director", re.I)

def sub_of(rec):
    return (rec.get("SUBCATNAME") or "").strip()

def title_of(rec):
    t = (rec.get("NEWSSUB") or "").strip()
    m = re.match(r"^(.*?)\s*-\s*\d{5,6}\s*-\s*(.*)$", t)
    return (m.group(2) if m else t).strip()

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
    if "earnings call transcript" in sub or ("analyst / investor meet" in sub and CONCALL_RX.search(text)):
        return "CONCALL"
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

def build_card(rec, tag):
    dt = parse_dt(rec)
    when = dt.strftime("%d %b %Y, %H:%M IST") if dt else ""
    head = title_of(rec)
    body = re.sub(r"\s+", " ", (rec.get("HEADLINE") or "").strip())
    if body.lower() == head.lower() or body.lower() in head.lower():
        body = ""
    more = re.sub(r"\s+", " ", (rec.get("MORE") or "").strip())
    detail = (body or more)[:700] or None
    it = {"tag": tag, "company": company_of(rec)[:48], "meta": f"BSE {rec.get('SCRIP_CD')}  |  {when}", "headline": head, "detail": detail, "source": "BSE announcement"}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"news_{rec['NEWSID']}.png")
    CM.render_news(it, path)
    cap = f"{tag.title()}: {it['company']} (BSE {rec.get('SCRIP_CD')})\n{head}\nFiling: {link(rec)}\n\n{DISC}"
    return path, cap

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

def send_photo(path, cap):
    import requests
    with open(path, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data={"chat_id": CHAT, "caption": cap[:1024]}, files={"photo": fh}, timeout=60)
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

_last = [0.0]

def tick(bse):
    """Called by the poll loop (live only). Returns (changed, lines)."""
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
                path, cap = build_card(r, tag)
                res = send_photo(path, cap)
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
