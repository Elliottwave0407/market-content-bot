"""One-off: Shipping Corporation of India Land and Assets Q2 FY27 standalone card from figures read by hand off the filing (Rs lakh), reconciled:
revenue + other income = total income; total income - expenses = PBT; PBT - tax = PAT in all three columns.
Renders always; sends (private chat with the usual buttons, public group with Filing only) only when CONFIRM=yes."""
import os, sys, time, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import nse_results as nse, pdf_card as pc, results_fetcher as rf, card
CONFIRM = os.environ.get("CONFIRM", "").lower() == "yes"
d = {"revenue": [767, 786, 613], "other_income": [2035, 1995, 2143], "total_income": [2802, 2781, 2756],
     "total_expenses": [1229, 959, 2169], "finance_costs": [0, 0, 0], "depreciation": [57, 65, 69],
     "pbt": [1573, 1822, 587], "tax": [398, 420, 168], "pat": [1175, 1402, 419], "eps": [0.25, 0.30, 0.09]}
try:
    ok = [nse.arith_col(d, i) for i in range(3)]
    p("reconciliation by column:", ok)
    assert all(ok)
    k = pc.K["lakh"]
    cur, prev, yago = (pc.to_m(d, i, k) for i in range(3))
    q = rf.qcode(2026, 9)
    empty = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
    res = {"basis": "standalone", "q": q, "note": "hand-read from the filing, arithmetic-checked", "yprev": None,
           "quarters": [{"q": rf.qlabel(q), "m": cur}, {"q": rf.qlabel(q - 1), "m": prev}, {"q": rf.qlabel(q - 2), "m": empty}, {"q": rf.qlabel(q - 3), "m": empty}, {"q": rf.qlabel(q - 4), "m": yago}]}
    x = {"sm_name": "Shipping Corporation of India Land and Assets Ltd", "symbol": "SCILAL", "attchmntFile": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/28885cb7-5ab7-40fe-a8ac-ffe0e16feae5.pdf"}
    os.makedirs(nse.OUTDIR, exist_ok=True)
    png = os.path.join(nse.OUTDIR, "sci_manual.png")
    card.render((x.get("sm_name") or x["symbol"]).strip(), "BSE 544142", "standalone", res["quarters"], png, yprev=None)
    cap, tweet = nse.post_card(x, res, png, "Sep-26")
    p("CARD:", cap.splitlines()[1], "| margin", round(100 * cur["ebitda"] / cur["revenue"], 1), "% | file", x["attchmntFile"].split("/")[-1][:50])
    if CONFIRM:
        import xbuttons, results_poller as rp
        cc, flink = xbuttons.split_link(cap)
        with open(png, "rb") as fh:
            rr = nse.tg("sendPhoto", data={"chat_id": nse.CHAT, "caption": cc[:1024], "reply_markup": xbuttons.markup(tweet, flink)}, files={"photo": fh})
        p("private sent ok =", rr.get("ok"))
        if rr.get("ok"):
            time.sleep(2)
            r2 = rp.mirror_to_channel(png, cc, flink, "x|x|standalone", force=True)
            p("public sent ok =", (r2 or {}).get("ok"))
            try:
                import store; store.log_result("nse", cap, rr, card.LAST, None)
            except Exception: pass
except Exception:
    import traceback; p("ERROR", traceback.format_exc()[-700:])
publish()
