"""Send FULL result cards for the listed BSE codes to the FinGod PUBLIC group only (Filing button only). Never touches the private groups or any state.
CODES = comma list of BSE codes; ONLYQ = quarter label to require (default Sep-26). Sends only when CONFIRM=yes, else builds and prints captions."""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
import xbuttons, channel_copy
try:
    codes = [c.strip() for c in os.environ.get("CODES", "").split(",") if c.strip()]
    order = {c: i for i, c in enumerate(codes)}
    rpl.DAYS_BACK = 1
    confirm = os.environ.get("CONFIRM", "").strip().lower() == "yes"
    done = []
    with BSE(download_folder="/tmp") as b:
        rows = None
        for _t in range(4):
            try: rows = rpl.fetch_filings(b); break
            except Exception as e:
                p("BSE fetch retry", _t + 1, type(e).__name__); time.sleep(20)
        if rows is None: raise RuntimeError("BSE not reachable")
        first = {}
        for r in rows:
            c = str(r.get("SCRIP_CD")).strip()
            if c in order and (c not in first or r["NEWS_DT"] < first[c]["NEWS_DT"]): first[c] = r
        p("filings found:", len(first), "of", len(codes))
        for c in codes:
            r = first.get(c)
            if not r: p("not found in window:", c); continue
            try:
                kind, text, png, key = rpl.build(b, r, final=True, age_min=100000)
            except Exception as e:
                p("build error", c, type(e).__name__); continue
            if kind != "photo" or not png or key.split("|")[-1] not in ("consolidated", "standalone") or key.split("|")[1] != os.environ.get("ONLYQ", "Sep-26"):
                p("skip (not a full Sep-26 card):", c, kind, key.split("|", 1)[-1]); continue
            cap, flink = xbuttons.split_link(text)
            p("CARD", (r.get("SLONGNAME") or "")[:26], key, "|", cap.split("\n")[1][:120] if "\n" in cap else cap[:120])
            if confirm:
                res = channel_copy.copy_photo(png, cap, flink)
                p("  sent ok =", bool(res and res.get("ok")), (res or {}).get("description", "")[:80]); done.append(c); time.sleep(2)
    p("sent:" if confirm else "dry run, not sent. built:", len(done) if confirm else "see CARD lines")
except Exception:
    p("ERROR", traceback.format_exc()[-800:])
publish()
