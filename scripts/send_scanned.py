"""Build FULL result cards for the listed BSE codes with the live reader (light model, then the stronger-model retry, key chain incl. the scanned-results key)
and send them to the private chat (usual buttons) and the FinGod public group (Filing only). Only full Sep-26 cards; anything else is skipped.
Sends only when CONFIRM=yes. Never touches state."""
import os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
import xbuttons, tags
try:
    codes = [c.strip() for c in os.environ.get("CODES", "").split(",") if c.strip()]
    confirm = os.environ.get("CONFIRM", "").lower() == "yes"
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    rpl.DAYS_BACK = 1
    os.makedirs(rpl.OUTDIR, exist_ok=True)
    rpl._ST = rpl.load_state()
    import pdf_card
    pdf_card.new_poll()
    rows, b = None, None
    for _t in range(8):
        try:
            ctx = BSE(download_folder="/tmp")
            b = ctx.__enter__()
            rows = rpl.fetch_filings(b)
            break
        except Exception as e:
            p("BSE fetch retry", _t + 1, type(e).__name__)
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass
            time.sleep(25)
    if rows is None:
        raise RuntimeError("BSE not reachable")
    first = {}
    for r in rows:
        c = str(r.get("SCRIP_CD")).strip()
        if c in codes and (c not in first or r["NEWS_DT"] < first[c]["NEWS_DT"]):
            first[c] = r
    p("filings found:", len(first), "of", len(codes))
    sent = 0
    for c in codes:
        r = first.get(c)
        if not r:
            p("not found:", c)
            continue
        got = None
        for attempt in range(3):
            kind, png, key, text = None, None, "", ""
            try:
                kind, text, png, key = rpl.build(b, r, final=True, age_min=100000)
            except Exception as e:
                p("build error", c, type(e).__name__)
            if kind == "photo" and png and key.split("|")[-1] in ("consolidated", "standalone") and key.split("|")[1] == "Sep-26":
                got = (text, png, key)
                break
            p("  attempt", attempt + 1, "no full card:", c, kind)
            time.sleep(20)
        if not got:
            p("SKIP (no full Sep-26 card):", c)
            continue
        text, png, key = got
        cap, flink = xbuttons.split_link(text)
        p("CARD", (r.get("SLONGNAME") or "")[:30], key, "|", cap.split("\n")[1][:130] if "\n" in cap else cap[:130])
        if confirm:
            nm = (r.get("SLONGNAME") or "").strip()
            ql = key.split("|")[1]
            tweet = "\n".join(text.split("\n")[:2]).replace(" | Consolidated", "").replace(" | Standalone", "") + "\n" + tags.join(tags.company_tag(code=r.get("SCRIP_CD"), name=nm), tags.quarter_tag(ql), "#Results")
            with open(png, "rb") as fh:
                rr = rpl.tg("sendPhoto", data={"chat_id": chat, "caption": cap[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
            p("  private ok =", rr.get("ok"))
            if rr.get("ok"):
                time.sleep(2)
                r2 = rpl.mirror_to_channel(png, cap, flink, key)
                p("  public ok =", (r2 or {}).get("ok"))
                sent += 1
            time.sleep(3)
    p("sent cards:", sent if confirm else "dry run")
except Exception:
    p("ERROR", traceback.format_exc()[-700:])
publish()
