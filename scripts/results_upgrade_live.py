"""Upgrade pass: filings that got a stub card ('code|quarter|na') get their FULL card now, if BSE has structured numbers.
Private results group: full card with all buttons. Public group: full card with Filing button only. Each company once (state/upgraded.json).
Sends only when CONFIRM=yes. Never touches state/seen.json."""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
import xbuttons
UP = "state/upgraded.json"
try:
    confirm = os.environ.get("CONFIRM", "").strip().lower() == "yes"
    chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    rpl.DAYS_BACK = int(os.environ.get("DAYS", "5")); rpl._ST = None       # no PDF/Gemini route
    os.makedirs(rpl.OUTDIR, exist_ok=True)
    st = json.load(open("state/seen.json"))
    stub = {k.split("|")[0]: k.split("|")[1] for k in st["posted"] if k.endswith("|na")}
    try: done = set(json.load(open(UP)))
    except Exception: done = set()
    rows = None; ctx = None
    for _t in range(8):
        try:
            ctx = BSE(download_folder="/tmp"); b = ctx.__enter__()
            rows = rpl.fetch_filings(b); break
        except Exception as e:
            p("BSE fetch retry", _t + 1, type(e).__name__)
            try: ctx.__exit__(None, None, None)
            except Exception: pass
            time.sleep(25)
    if rows is None: raise RuntimeError("BSE not reachable")
    first = {}
    for r in rows:
        c = str(r.get("SCRIP_CD")).strip()
        if c in stub and f"{c}|{stub[c]}" not in done and (c not in first or r["NEWS_DT"] < first[c]["NEWS_DT"]): first[c] = r
    p("stub filings in window:", len(first), "| already upgraded:", len(done))
    sent = 0
    for c, r in sorted(first.items(), key=lambda x: x[1]["NEWS_DT"]):
        nm = (r.get("SLONGNAME") or "").strip()
        try:
            kind, text, png, key = rpl.build(b, r, final=True, age_min=100000)
        except Exception as e:
            p("skip build error", nm[:24], type(e).__name__); continue
        full = key.split("|")[-1] in ("consolidated", "standalone")
        bad = ("Rs 0.0 Cr" in text or "(- YoY)" in text or "Sales Rs -" in text or "Sales Rs 0." in text or key.split("|")[1] != "Sep-26")
        if kind != "photo" or not png or not full or bad or key.split("|")[1] != stub[c]:
            p("skip", nm[:24], kind, key.split("|", 1)[-1], "bad" if bad else ""); continue
        cap, flink = xbuttons.split_link(text)
        ql = key.split("|")[1]
        tweet = "\n".join(text.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + rpl.tags.join(rpl.tags.company_tag(code=r.get("SCRIP_CD"), name=nm), rpl.tags.quarter_tag(ql), "#Results")
        p("CARD", nm[:26], key, "|", cap.split("\n")[1][:110] if "\n" in cap else cap[:110])
        if not confirm: continue
        with open(png, "rb") as fh:
            res = rpl.tg("sendPhoto", data={"chat_id": chat, "caption": cap[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
        p("  private ok =", res.get("ok"), rpl.redact(res.get("description", "")))
        if not res.get("ok"): continue
        rpl.mirror_to_channel(png, cap, flink, key)
        try:
            import store; store.log_result("bse-upgrade", text, res, rpl.card.LAST, r.get("NEWS_DT"))
        except Exception: pass
        done.add(f"{c}|{stub[c]}"); sent += 1
        os.makedirs("state", exist_ok=True); json.dump(sorted(done), open(UP, "w"))
        time.sleep(3)
    p("sent:" if confirm else "dry run, would send:", sent if confirm else "see CARD lines")
except Exception:
    p("ERROR", traceback.format_exc()[-800:])
publish()
