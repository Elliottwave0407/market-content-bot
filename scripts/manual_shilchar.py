"""One-off: Shilchar Technologies Q2 FY27 standalone card from figures read by hand off the filing (Rs lakh), reconciled:
revenue + other income = total income; total income - expenses = PBT; PBT - tax = PAT in all three columns.
Renders always; sends (private chat with the usual buttons, public group with Filing only) only when CONFIRM=yes."""
import os, sys, time, json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import nse_results as nse, pdf_card as pc, results_fetcher as rf, card
CONFIRM = os.environ.get("CONFIRM", "").lower() == "yes"
d = {"revenue": [19261.31, 13460.71, 17128.20], "other_income": [679.67, 717.62, 907.07], "total_income": [19940.98, 14178.34, 18035.27],
     "total_expenses": [15371.99, 11370.86, 11878.30], "finance_costs": [9.62, 9.92, 9.37], "depreciation": [107.54, 105.75, 100.76],
     "pbt": [4568.99, 2807.47, 6156.97], "tax": [1271.31, 720.99, 1563.21], "pat": [3297.68, 2086.48, 4593.76], "eps": [28.83, 18.24, 40.15]}
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
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    rows = [x for x in nse.result_rows(nse.fetch_day(now)) if x["symbol"].upper() == "SHILCTECH"]
    assert rows, "filing row not found"
    x = sorted(rows, key=lambda r: str(r.get("sort_date") or ""))[-1]
    os.makedirs(nse.OUTDIR, exist_ok=True)
    png = os.path.join(nse.OUTDIR, "shilchar_manual.png")
    card.render((x.get("sm_name") or x["symbol"]).strip(), "BSE 531201", "standalone", res["quarters"], png, yprev=None)
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
