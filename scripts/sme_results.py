"""SME half-yearly results route (BSE-SME companies file half-yearly, as PDFs only).
Called by the poll loop (tick) when posting is on; dry run by day via the sme-results-test workflow (SME_DAY).
Safe by design: any failure here is logged and ignored; a filing that is not half-yearly is left to the normal quarterly route."""
import os, sys, json, time, tempfile, requests
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p
import card, tags, pdf_card as pc, results_fetcher as rf, sme_half as sh
import nse_results as nse
IST = timezone(timedelta(hours=5, minutes=30))
ST, CODES_F = "state/sme_results.json", "state/sme_codes.json"
OUTDIR = os.environ.get("OUT_DIR", "out")
SEND = os.environ.get("POLL_SEND", os.environ.get("SME_SEND", "0")) == "1"
DAILY_CAP = int(os.environ.get("SME_DAILY_CAP", "40"))      # PDF reads per day (free Gemini quota is shared with the main route)
LIVE = os.environ.get("SME_LIVE", "0") == "1"      # the poll loop only runs this route when SME_LIVE=1 is set in results-poll.yml (off until dry runs are approved)
_S = {"last_tick": 0.0, "scan_at": 0.0, "cands": []}
TRY = {}

def load():
    try: return json.load(open(ST))
    except Exception: return {"posted": [], "done": [], "use": {}}

def save(st):
    os.makedirs("state", exist_ok=True)
    st["done"] = st["done"][-3000:]; st["posted"] = st["posted"][-1500:]
    json.dump(st, open(ST, "w"))

def sme_codes(bse):
    """BSE SME scrip codes (groups M, MT, MS); refreshed weekly."""
    try:
        d = json.load(open(CODES_F))
        if time.time() - d.get("at", 0) < 7 * 86400 and d.get("codes"): return set(d["codes"])
    except Exception: pass
    codes = set()
    for g in ("M", "MT", "MS"):
        try:
            for x in bse.listSecurities(group=g): codes.add(str(x.get("SCRIP_CD")).strip())
        except Exception as e: p("  SME list failed", g, repr(e)[:50])
    if codes:
        os.makedirs("state", exist_ok=True); json.dump({"at": time.time(), "codes": sorted(codes)}, open(CODES_F, "w"))
    return codes

def scan(bse, start, end):
    codes = sme_codes(bse); out, pg, tot = [], 1, 0
    while pg <= 60:
        d = None
        for t in range(3):
            try: d = bse.announcements(page_no=pg, from_date=start, to_date=end, category="Result"); break
            except Exception: time.sleep(4)
        t_ = (d or {}).get("Table", [])
        if not t_: break
        tot += len(t_)
        out += [r for r in t_ if str(r.get("SCRIP_CD")).strip() in codes and r.get("ATTACHMENTNAME")]
        if tot >= ((d.get("Table1") or [{}])[0].get("ROWCNT", 0) or 0): break
        pg += 1
    return out

def half_label(ql):
    try:
        d = datetime.strptime(ql, "%b-%y"); fy = d.year + (1 if d.month > 3 else 0)
        return f"{'H1' if d.month == 9 else 'H2'} FY{str(fy)[2:]}"
    except Exception: return ql

def process(bse, r, st, final=False):
    nid, code, name = str(r["NEWSID"]), str(r["SCRIP_CD"]).strip(), (r.get("SLONGNAME") or str(r["SCRIP_CD"])).strip()
    if TRY.get(nid, (0, 0))[0] >= 3 or time.time() - TRY.get(nid, (0, 0))[1] < 240: return "skip"
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 19800))
    if st["use"].get(day, 0) >= DAILY_CAP: return "skip"
    TRY[nid] = (TRY.get(nid, (0, 0))[0] + 1, time.time())
    content = b""
    for folder in ("AttachLive", "AttachHis"):
        try: rr = requests.get(f"https://www.bseindia.com/xml-data/corpfiling/{folder}/{r['ATTACHMENTNAME']}", headers=pc.UA, timeout=45)
        except Exception: continue
        if rr.content[:4] == b"%PDF": content = rr.content; break
    if not content or len(content) > 15_000_000: p(f"  {name}: PDF not downloadable"); return "wait"
    st["use"][day] = st["use"].get(day, 0) + 1
    res, why = sh.read_half_card(content, pc.geminikey(), name)
    if res is None:
        if why.startswith("not a half-yearly") or why.startswith("half-year end month"):
            p(f"  {name}: {why} - left to the quarterly route"); return "done"
        p(f"  {name}: not postable - {why}")
        return "wait" if TRY[nid][0] < 3 else "done"
    ql = rf.qlabel(res["q"]); key = f"SME|{code}|{ql}|{res['basis']}"; bkey = f"{code}|{ql}|{res['basis']}"
    if key in st["posted"] or bkey in nse._seen_posted():
        p(f"  dup skip {key}"); return "done"
    os.makedirs(OUTDIR, exist_ok=True)
    png = os.path.join(OUTDIR, f"sme_{code}_{ql}_{res['basis']}.png")
    v = card.render(name, f"BSE {code}", res["basis"], res["quarters"], png, filed_note="Half-yearly results, read from the filing PDF; arithmetic-checked.", half=True)
    cur, yago = res["quarters"][0]["m"], res["quarters"][4]["m"]
    sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
    sd, pd_ = (0 if sales and sales >= 100 else 1), (0 if pat and pat >= 100 else 1)
    sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
    lk = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{r['ATTACHMENTNAME']}"
    cap = (f"{name} {half_label(ql)} (half-year) | {res['basis'].capitalize()}\n"
           f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
           f"Read from the filing PDF (BSE SME half-yearly; arithmetic-checked). Filing: {lk}\n\n{nse.DISC}")
    tweet = "\n".join(cap.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(code=code, name=name), "#Results", "#HalfYearlyResults")
    p(f"  [sme card] {key} verdict={v} :: {cap.splitlines()[1]}")
    if SEND and nse.CHAT:
        import xbuttons
        cc, flink = xbuttons.split_link(cap)
        with open(png, "rb") as fh:
            rs = nse.tg("sendPhoto", data={"chat_id": nse.CHAT, "caption": cc[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
        p(f"  sent ok={rs.get('ok')}")
        if not rs.get("ok"): return "wait"
        time.sleep(3.2)
    st["posted"].append(key); nse._mark_seen(bkey)
    return "done"

def run_once(day=None, maxn=1):
    from bse import BSE
    now = datetime.now(IST)
    start, end = ((day, day) if day else (now - timedelta(days=1), now))
    st = load(); changed = False
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        if day or time.time() - _S["scan_at"] > 600:
            _S["cands"] = scan(b, start.replace(tzinfo=None), end.replace(tzinfo=None)); _S["scan_at"] = time.time()
            p(f"SME result filings with PDF in window: {len(_S['cands'])}")
        n = 0
        for r in sorted(_S["cands"], key=lambda r: r.get("NEWS_DT", "")):
            if str(r["NEWSID"]) in st["done"]: continue
            out = process(b, r, st)
            if out == "done": st["done"].append(str(r["NEWSID"])); changed = True
            if out != "skip": n += 1
            if n >= maxn: break
    if changed and not day: save(st)
    return changed

def tick():
    """Poll-loop hook (live only). Returns (changed, lines). Never raises."""
    if not (LIVE and SEND and nse.CHAT) or time.time() - _S["last_tick"] < 60: return False, []
    _S["last_tick"] = time.time()
    import ci_out
    n0 = len(ci_out.OUT)
    try: ch = run_once(maxn=1)
    except Exception as e:
        p("sme results ERROR:", repr(e)[:200].replace(nse.TOKEN, "<token>") if nse.TOKEN else repr(e)[:200]); ch = False
    return ch, ci_out.OUT[n0:]

if __name__ == "__main__":
    from ci_out import publish
    d = os.environ.get("SME_DAY", "").strip()
    try: run_once(datetime.strptime(d, "%Y-%m-%d") if d else None, maxn=int(os.environ.get("SME_MAX", "8")))
    except Exception:
        import traceback; p("ERROR", traceback.format_exc()[-900:])
    publish()
