"""One-off: replace 'Numbers not shown' stub cards with full cards built from NSE's own structured numbers (nse_backup).
Env: FILL_SEND (1 = post to Telegram, 0 = dry run: render + log only), FILL_LIMIT (max posts, 0 = all), TELEGRAM_*.
Own state file (state/stub_fill.json) so the live poller's state is never touched. A company/quarter already holding a full card is skipped."""
import os, sys, json, time, tempfile
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
os.environ["NSE_BACKUP"] = "1"
import results_poller as rp
import nse_backup, card, xbuttons, tags, store
from ci_out import p, publish
from bse import BSE

SEND = os.environ.get("FILL_SEND", "0") == "1"
LIMIT = int(os.environ.get("FILL_LIMIT", "0"))
ONLY = os.environ.get("FILL_ONLY", "").strip()  # e.g. "530549|Sep-26": restrict to one company/quarter
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
F = "state/stub_fill.json"
try: fs = json.load(open(F))
except Exception: fs = {"done": {}, "none": {}}
seen = json.load(open("state/seen.json"))
posted = set(seen["posted"])
stubs = sorted({k for k in posted if k.endswith("|na")})
todo = []
for k in stubs:
    code, label = k.split("|")[:2]
    if any(f"{code}|{label}|{b}" in posted for b in ("consolidated", "standalone")): continue
    if f"{code}|{label}" in fs["done"]: continue
    if ONLY and f"{code}|{label}" != ONLY: continue
    todo.append((code, label))
todo.sort(key=lambda x: -rp.pdf_card.mcap_of(x[0]))
p("stub cards without a full card:", len(todo))
os.makedirs(rp.OUTDIR, exist_ok=True)
n_ok = n_none = n_sent = 0
with BSE(download_folder=tempfile.mkdtemp()) as bse:
    for code, label in todo:
        if LIMIT and n_sent >= LIMIT: break
        rec = None
        for t in range(3):
            try:
                rows = bse.announcements(scripcode=code, from_date=datetime(2026, 10, 1), to_date=datetime.now(), category="Result").get("Table", [])
                rows = [r for r in rows if r.get("ATTACHMENTNAME")]
                rec = sorted(rows, key=lambda r: r.get("NEWS_DT", ""))[-1] if rows else None
                break
            except Exception: time.sleep(4)
        if not rec: n_none += 1; continue
        name = (rec.get("SLONGNAME") or code).strip()
        headline = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
        cons_exp = bool(seen.get("cons_expected", {}).get(str(rec["NEWSID"]))) or "consolidated" in headline.lower()
        nsq = nse_backup.get(code, label, cons_exp)
        if not nsq: n_none += 1; p("  no NSE numbers:", name); continue
        basis, quarters, yprev = nsq["basis"], nsq["quarters"], nsq["yprev"]
        cur, prev, yago = quarters[0]["m"], quarters[1]["m"], quarters[4]["m"]
        sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
        r0, r1 = cur.get("revenue"), prev.get("revenue")
        if (r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50)) or not rp.size_ok(code, sales):
            n_none += 1; p("  fails sanity checks:", name); continue
        sd, pd_ = (0 if sales and sales >= 100 else 1), (0 if pat and pat >= 100 else 1)
        sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
        png = os.path.join(rp.OUTDIR, f"{code}_{label}_{basis}.png")
        card.render(name, f"BSE {code}", basis, quarters, png, yprev=yprev)
        lk = rp.link(rec)
        cap = (f"{name} {rp.fy_label(label)} | {basis.capitalize()}\n"
               f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
               f"Filing: {lk}\n\n{rp.DISC}")
        key = f"{code}|{label}|{basis}"
        n_ok += 1
        p(f"[fill] {key} :: {cap.splitlines()[1]}")
        if SEND and CHAT:
            cc, flink = xbuttons.split_link(cap)
            tweet = "\n".join(cap.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(code=code, name=name), tags.quarter_tag(label), "#Results")
            with open(png, "rb") as fh:
                r = rp.tg("sendPhoto", data={"chat_id": CHAT, "caption": cc[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
            p(f"  sent ok={r.get('ok')} {rp.redact(r.get('description', ''))}")
            if not r.get("ok"): continue
            rp.mirror_to_channel(png, cc, flink, key)
            try: store.log_result("bse", cap, r, card.LAST, rec.get("NEWS_DT"))
            except Exception: pass
            fs["done"][f"{code}|{label}"] = key; n_sent += 1
            json.dump(fs, open(F, "w"))
            time.sleep(3.2)
p(f"summary: replaceable {n_ok}, no NSE numbers or failed checks {n_none}, sent {n_sent}")
publish()
