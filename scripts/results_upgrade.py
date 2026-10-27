"""DRY RUN: for result filings that got a STUB card (state key 'code|quarter|na'), build the full card now if BSE has structured numbers.
Writes the card pictures to out/upgrade/ and prints captions. Sends NOTHING, uses NO Gemini, changes NO state."""
import os, sys, json, shutil, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
from bse import BSE
import results_poller as rpl
try:
    rpl.DAYS_BACK = int(os.environ.get("DAYS", "5")); rpl._ST = None      # None = no PDF/Gemini route inside build()
    st = json.load(open("state/seen.json"))
    stub = {k.split("|")[0]: k.split("|")[1] for k in st["posted"] if k.endswith("|na")}
    os.makedirs("out/upgrade", exist_ok=True)
    built = []; other = {}
    with BSE(download_folder="/tmp") as b:
        rows = rpl.fetch_filings(b)
        first = {}
        for r in rows:
            c = str(r.get("SCRIP_CD")).strip()
            if c in stub and (c not in first or r["NEWS_DT"] < first[c]["NEWS_DT"]): first[c] = r
        p("stub filings in window:", len(first))
        for c, r in sorted(first.items(), key=lambda x: x[1]["NEWS_DT"]):
            try:
                kind, text, png, key = rpl.build(b, r, final=True, age_min=100000)
            except Exception as e:
                other[r["SLONGNAME"][:24]] = "error " + type(e).__name__; continue
            mcv = (json.load(open("state/mcap_cache.json")).get(c) or [0])[0] if os.path.exists("state/mcap_cache.json") else 0
            if kind == "photo" and png and not key.endswith("|na") and mcv < 500:
                other[r["SLONGNAME"][:24]] = "small (<500 cr), skipped"; continue
            if kind == "photo" and png and not key.endswith("|na"):
                dst = f"out/upgrade/{c}_{key.split('|')[1]}.png"; shutil.copy(png, dst)
                built.append((r["SLONGNAME"], key)); p("FULL CARD:", r["SLONGNAME"][:28], key, "|", text.split("\n")[1][:150] if "\n" in text else text[:150])
            else:
                other[r["SLONGNAME"][:24]] = f"{kind}:{key.split('|')[-1]}"
    p("upgradable to a full card now:", len(built), "| still stub/other:", len(other))
    p("others:", json.dumps(other)[:900])
except Exception:
    p("ERROR", traceback.format_exc()[-900:])
publish()
