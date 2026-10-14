"""Daily market posters: FII/DII (with month-to-date table) and bulk/block deals.
Usage: python scripts/market_posts.py fii|deals|both
Env: POST_SEND=1 posts to the Telegram group and saves state; otherwise a dry run (PNGs only, state untouched).
     POST_FORCE=1 ignores the 'already posted' check (use with POST_SEND=0 to preview).
     OUT_DIR = where PNGs go (default ./out)."""
import os, re, sys, json, time, subprocess
from datetime import datetime, timedelta, timezone
import requests

sys.path.insert(0, os.path.dirname(__file__))
import tags
from ci_out import p, publish
import cards_market as CM

SEND = os.environ.get("POST_SEND", "0") == "1"
FORCE = os.environ.get("POST_FORCE", "0") == "1"
OUT = os.environ.get("OUT_DIR", "out")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("MARKET_CHAT_ID", "").strip()   # the separate market/news group (NOT the results group)
X_BUTTON = os.environ.get("X_BUTTON", "1") == "1"   # attach a "Post to X" button under cards that have a tweet text
COMMIT = True      # False when run inside the poll loop (the loop commits state itself)
QUIET = False
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36", "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
HIST = "state/fii_dii_history.json"
POSTED = "state/market_posted.json"
IST = timezone(timedelta(hours=5, minutes=30))

def jload(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default

def jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1)

def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True)

def commit_state():
    git("config", "user.name", "market-content-bot")
    git("config", "user.email", "bot@users.noreply.github.com")
    git("add", "state")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", "Market posts state")
        for _ in range(4):
            if git("pull", "--rebase", "-q", "origin", "main").returncode == 0 and git("push", "-q", "origin", "main").returncode == 0:
                return
            time.sleep(2)

def x_url(text):
    from urllib.parse import quote
    return "https://x.com/intent/tweet?text=" + quote(text[:270])

def send_photo(path, caption, tweet=None):
    data = {"chat_id": CHAT, "caption": caption[:1024]}
    if tweet and X_BUTTON:
        import xbuttons
        data["reply_markup"] = xbuttons.markup(tweet)
    with open(path, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data=data, files={"photo": fh}, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False}

def post(paths_captions):
    """Returns True only if every photo was accepted."""
    if not SEND or not CHAT:
        p("DRY RUN (send off or no market group set) - not sent:", [pc[0] for pc in paths_captions])
        return False
    ok = True
    for item in paths_captions:
        path, cap = item[0], item[1]
        r = send_photo(path, cap, item[2] if len(item) > 2 else None)
        p("sent", path, r.get("ok"), (r.get("description") or "")[:80])
        ok = ok and bool(r.get("ok"))
        time.sleep(3.2)
    return ok

def num(s):
    return float(str(s).replace(",", ""))

# ------------------------------------------------------------------ FII / DII
def fetch_fii_dii():
    s = requests.Session()
    s.headers.update(UA)
    s.get("https://www.nseindia.com/reports/fii-dii", timeout=20)
    r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", headers={"Referer": "https://www.nseindia.com/reports/fii-dii"}, timeout=20)
    data = r.json()
    out = {}
    for x in data:
        key = "fii" if x["category"].upper().startswith("FII") else "dii" if x["category"].upper().startswith("DII") else None
        if key:
            out[key] = {"buy": num(x["buyValue"]), "sell": num(x["sellValue"]), "net": num(x["netValue"])}
            out["date"] = datetime.strptime(x["date"], "%d-%b-%Y")
    if "fii" not in out or "dii" not in out:
        raise ValueError("FII/DII rows missing in NSE response")
    return out

def fivepaisa_mtd():
    """Month-till-date cash FII/DII from 5paisa (used once to seed earlier days of the month)."""
    r = requests.get("https://www.5paisa.com/share-market-today/fii-dii-data", headers=UA, timeout=25)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    m = re.search(r"Month till date ([\d,\.\-]+) ([\d,\.\-]+) ([\d,\.\-]+) ([\d,\.\-]+) ([\d,\.\-]+) ([\d,\.\-]+)", txt)
    if not m:
        return None
    v = [num(x) for x in m.groups()]
    return {"fii_buy": v[0], "fii_sell": v[1], "fii_net": v[2], "dii_buy": v[3], "dii_sell": v[4], "dii_net": v[5]}

def idle(msg):
    if not QUIET:
        p(msg)
    return False

_sess = {"s": None, "t": 0}

def do_fii():
    """Returns True if it posted (state changed)."""
    today_ist = datetime.now(IST).strftime("%Y-%m-%d")
    if QUIET and jload(HIST, {}).get("posted", "") >= today_ist:
        return False                      # today's card already out: no more requests until tomorrow
    d = fetch_fii_dii()
    day = d["date"]
    iso = day.strftime("%Y-%m-%d")
    hist = jload(HIST, {"days": [], "posted": ""})
    if not QUIET:
        p("FII/DII date from NSE:", iso, "| last posted:", hist.get("posted") or "-")
    if iso <= hist.get("posted", "") and not FORCE:
        return idle("Nothing new to post.")
    days = [x for x in hist["days"] if x["date"] != iso]
    today = {"date": iso, "label": day.strftime("%d %b"), "fii_buy": d["fii"]["buy"], "fii_sell": d["fii"]["sell"], "fii_net": d["fii"]["net"],
             "dii_buy": d["dii"]["buy"], "dii_sell": d["dii"]["sell"], "dii_net": d["dii"]["net"]}
    month_key = iso[:7]
    this_month = [x for x in days if x["date"][:7] == month_key]
    if not this_month and day.day > 3:
        # first run mid-month: build ONE combined row for the earlier days from 5paisa's month-till-date total
        try:
            m = fivepaisa_mtd()
            if m:
                seed = {k: round(m[k] - today[k], 2) for k in m}
                if all(seed[k] >= 0 for k in ("fii_buy", "fii_sell", "dii_buy", "dii_sell")) and seed["fii_buy"] > 0:
                    seed.update({"date": f"{month_key}-00", "label": f"1-{day.day - 1} {day.strftime('%b')}", "combined": True})
                    days.append(seed)
                    p("Seeded earlier days:", seed)
                else:
                    p("5paisa MTD did not look consistent; no seed row", m)
        except Exception as e:
            p("Seed failed:", repr(e)[:150])
    days.append(today)
    days.sort(key=lambda x: x["date"])
    month_rows = [x for x in days if x["date"][:7] == month_key]
    card = {"date": day.strftime("%d %b %Y"), "month": day.strftime("%b %Y"), "fii": d["fii"], "dii": d["dii"],
            "mtd": [{**x, "date": x["label"]} for x in month_rows]}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"fii_dii_{iso}.png")
    note = "Earlier days of the month shown as one combined row." if any(x.get("combined") for x in month_rows) else ""
    CM.render_fii_dii(card, path, note)
    f, dd = d["fii"]["net"], d["dii"]["net"]
    tot = lambda k: sum(x[k] for x in month_rows)
    cap = (f"FII/DII activity - {card['date']} (cash market, ₹ Cr)\n"
           f"FII/FPI: bought {d['fii']['buy']:,.0f} | sold {d['fii']['sell']:,.0f} | net {f:+,.0f}\n"
           f"DII: bought {d['dii']['buy']:,.0f} | sold {d['dii']['sell']:,.0f} | net {dd:+,.0f}\n"
           f"Month to date: FII {tot('fii_net'):+,.0f} | DII {tot('dii_net'):+,.0f}\n"
           f"Source: NSE provisional data.")
    tweet = (f"FII/DII activity - {card['date']} (cash, ₹ Cr)\n"
             f"FII net {f:+,.0f} | DII net {dd:+,.0f}\n"
             f"Month to date: FII {tot('fii_net'):+,.0f} | DII {tot('dii_net'):+,.0f}\n"
             f"#FIIDII #Nifty #StockMarketIndia")
    if post([(path, cap, tweet)]) and SEND:
        hist = {"days": [x for x in days if x["date"][:7] >= (day - timedelta(days=100)).strftime("%Y-%m")], "posted": iso}
        jsave(HIST, hist)
        if COMMIT:
            commit_state()
        p("FII/DII posted; history saved.")
        return True
    return False

# ------------------------------------------------------------------ bulk / block deals
_deals_seen = {}

def do_deals():
    """Returns True if it posted (state changed)."""
    if QUIET and jload(POSTED, {}).get("deals", "") >= datetime.now(IST).strftime("%Y-%m-%d"):
        return False
    import bulk_deals_pipeline as bp
    from bse import BSE
    bulk = bp.nse_rows()
    try:
        block = bp.nse_rows("https://nsearchives.nseindia.com/content/equities/block.csv")
    except Exception as e:
        p("block.csv failed:", repr(e)[:120])
        block = []
    seen = {(x["sym"], x["client"], x["side"], x["qty"], x["price"], x["date"]) for x in bulk}
    block = [x for x in block if (x["sym"], x["client"], x["side"], x["qty"], x["price"], x["date"]) not in seen]  # same trade can sit in both files
    nse = bulk + block
    if not nse:
        return idle("No NSE rows.")
    day = max(x["date"] for x in nse)
    nse = [x for x in nse if x["date"] == day]
    iso = day.strftime("%Y-%m-%d")
    posted = jload(POSTED, {})
    if iso <= posted.get("deals", "") and not FORCE:
        return idle("Nothing new to post.")
    p("Deals date:", iso, "| NSE rows:", len(nse), "| last posted:", posted.get("deals") or "-")
    if QUIET and not FORCE:                # wait until the NSE file has stopped growing (two reads in a row agree)
        if _deals_seen.get(iso) != len(nse):
            _deals_seen[iso] = len(nse)
            p("NSE deals file just appeared/changed; confirming on next check.")
            return False
    with BSE(download_folder="./") as bse:
        brows = bp.bse_rows(bse, day)
        now = datetime.now(IST)
        if not brows and now.hour < 21 and not FORCE:
            return idle("BSE deals not out yet; waiting (will accept NSE-only after 21:00 IST).")
        rows = nse + brows
        recs = bp.bse_universe(bse)
        bp.resolve(rows, recs, bp.nse_isins())
        kept = bp.net_deals(rows)
        bp.enrich(bse, kept)
    miss = sorted(set(x["name"] for x in kept if x["ex"] == "N" and not x["rec"]))
    p(f"raw {len(rows)} | kept {len(kept)} | BSE rows {len(brows)} | unmapped NSE: {miss}")
    if not kept:
        return idle("No qualifying deals.")
    label = day.strftime("%d %b %Y")
    os.makedirs(OUT, exist_ok=True)
    paths = CM.render_deals([{k: v for k, v in x.items() if k != "rec"} for x in kept], label, os.path.join(OUT, f"deals_{iso}"))
    nb = len([x for x in kept if x["side"] == "B"])
    ns = len(kept) - nb
    pc = []
    for i, path in enumerate(paths, 1):
        cap = (f"Bulk & block deals - {label}: {len(kept)} deals ({nb} net buys, {ns} net sells), card {i}/{len(paths)}\n"
               f"Netted per client per exchange; algo/prop trades and deals under ₹0.1 Cr removed.\nSource: NSE & BSE.") if i == 1 else f"Bulk & block deals - {label}, card {i}/{len(paths)}"
        tw = (f"Bulk & block deals - {label}: {len(kept)} deals ({nb} net buys, {ns} net sells). "
              f"Biggest: " + ", ".join(f"{x['name'][:22]} {x['cr']:,.0f} Cr" for x in sorted(kept, key=lambda z: -z['cr'])[:3]) + "\n" + tags.join("#BulkDeals", *[tags.company_tag(code=(x["rec"]["SCRIP_CD"] if x.get("rec") else None), name=x["name"], symbol=x.get("sym") or None) for x in sorted(kept, key=lambda z: -z['cr'])[:2]], "#StockMarketIndia")) if i == 1 else None
        pc.append((path, cap, tw))
    if post(pc) and SEND:
        posted["deals"] = iso
        jsave(POSTED, posted)
        if COMMIT:
            commit_state()
        p("Deals posted; state saved.")
        return True
    return False

_last_tick = [0.0]

def tick():
    """Called by the poll loop (live only). Cheap checks every ~30 s, weekdays 17:30-23:30 IST. Returns (changed, lines)."""
    global COMMIT, QUIET
    now = datetime.now(IST)
    if not (SEND and CHAT) or now.weekday() >= 5 or not (17.5 <= now.hour + now.minute / 60 <= 23.5):
        return False, []
    if time.time() - _last_tick[0] < 30:
        return False, []
    _last_tick[0] = time.time()
    COMMIT, QUIET = False, True
    n0 = len(__import__("ci_out").OUT)
    changed = False
    for name, fn in (("fii", do_fii), ("deals", do_deals)):
        try:
            changed = bool(fn()) or changed
        except Exception as e:
            p(f"market {name} ERROR:", repr(e)[:200].replace(TOKEN, "<token>") if TOKEN else repr(e)[:200])
    return changed, __import__("ci_out").OUT[n0:]

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    for name, fn in (("fii", do_fii), ("deals", do_deals)):
        if mode in (name, "both"):
            try:
                fn()
            except Exception as e:
                p(f"{name} ERROR:", repr(e)[:300])
    publish()

if __name__ == "__main__":
    main()
