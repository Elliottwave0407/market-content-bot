"""STEP 1 RCA (read-only): which companies filed a result on NSE (mainboard + SME) but have NO card at all?
Universe = every NSE result filing (equities + sme announcement indexes) from START to END. Cards = store/results keys + state/latency.log 'ready' lines (stub cards count as a card but are listed separately).
Prints: totals, the missing list with a reason class, and the stub list. Env: START, END (YYYY-MM-DD)."""
import os, sys, re, json, glob, time, collections
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["NSE_SME"] = "1"
import nse_results as nr

_t = datetime.utcnow() + timedelta(hours=5, minutes=30)
START = os.environ.get("START") or (_t - timedelta(days=2)).strftime("%Y-%m-%d")
END = os.environ.get("END") or _t.strftime("%Y-%m-%d")
d0, d1 = datetime.strptime(START, "%Y-%m-%d"), datetime.strptime(END, "%Y-%m-%d")
rows, day = [], d0
while day <= d1:
    try:
        rows += nr.result_rows(nr.fetch_day(day.replace(tzinfo=nr.IST)))
    except Exception as e:
        print("fetch error", day.date(), repr(e)[:60], flush=True)
    day += timedelta(days=1)
print("result filings fetched:", len(rows), flush=True)
maps = nr.bse_maps()
sym_of = json.load(open("state/symbols.json")).get("m", {})            # BSE code -> NSE symbol
code_of = {v: k for k, v in sym_of.items()}

cards, stubs = {}, {}
for f in glob.glob("store/results/*.jsonl"):
    for l in open(f, encoding="utf-8"):
        try: j = json.loads(l)
        except Exception: continue
        k = str(j.get("key") or ""); t = str(j.get("ticker") or "")
        ident = k.split("|")[0].replace("BSE ", "") if k.startswith("BSE") else (k.split("|")[1] if k.startswith("NSE|") else t.replace("BSE ", "").replace("NSE ", ""))
        cards[ident] = j.get("ts")
for l in open("state/latency.log", encoding="utf-8", errors="ignore"):
    m = re.search(r" ready (\S+?)\|(\S+?)\|(\S+)", l)
    if m:
        (stubs if m.group(3) in ("na", "nocons", "incomplete", "anomaly", "unverified") else cards).setdefault(m.group(1), l[:15])
        if m.group(3) in ("na", "nocons", "incomplete", "anomaly", "unverified"): stubs[m.group(1)] = l.strip()[:220]
try:      # seen.json 'posted' holds every card key, including stubs ('code|Sep-26|na')
    for k in json.load(open("state/seen.json"))["posted"]:
        a = k.split("|")
        if len(a) >= 3 and a[1] in ("Sep-26", "Jun-26", "Mar-26", "Dec-25") and not k.startswith("NSE"):
            (stubs if a[2] in ("na", "nocons", "incomplete", "anomaly", "unverified") else cards).setdefault(a[0], k)
            if a[2] in ("na", "nocons", "incomplete", "anomaly", "unverified"): stubs[a[0]] = k
except Exception as e:
    print("seen.json read error", repr(e)[:60])
nse_posted = set()
try: done_ids = set(map(str, json.load(open("state/nse_results.json"))["done"]))
except Exception: done_ids = set()
try:
    nse_posted = {k.split("|")[1] for k in json.load(open("state/nse_results.json"))["posted"]}
except Exception: pass

seen, miss, ok, stub = {}, [], [], []
for x in rows:
    sym = x["symbol"]
    if sym in seen: continue
    seen[sym] = 1
    code = None
    try: code = nr.bse_code(x, maps)
    except Exception: code = None
    code = str(code) if code else code_of.get(sym)
    isin = x.get("sm_isin") or ""
    has = (code and code in cards) or sym in cards or isin in cards or sym in nse_posted or isin in nse_posted
    if has: ok.append(sym)
    elif code and code in stubs: stub.append((sym, code, stubs[code]))
    else:
        board = "SME" if "emerge" in (x.get("smIndustry") or "").lower() or x.get("sm_isin", "")[:0] == "x" else "?"
        why = ("nse_done_no_card" if str(x.get("seq_id")) in done_ids else "never_processed_by_nse_route") + ("|bank_or_ins" if nr._fin_sym(sym) else "") + ("|sme_index" if (x.get("smIndustry") is not None and not code) else "")
        miss.append((sym, code, x.get("an_dt"), why, (x.get("attchmntText") or "")[:90].replace("\n", " ")))
print(f"UNIVERSE {len(seen)} companies | with a numbers card {len(ok)} | stub card only {len(stub)} | NO CARD {len(miss)}", flush=True)
cls = collections.Counter(("no_bse_code" if not m[1] else "has_bse_code") for m in miss)
print("MISSING by class:", dict(cls), flush=True)
for m in sorted(miss, key=lambda z: z[2] or ""): print("MISS", *m, sep=" | ", flush=True)
for s in stub[:80]: print("STUB", s[0], s[1], s[2][40:210], flush=True)

if os.environ.get("WRITE") == "1":      # the 'filed but no card' watch: anything filed more than 60 min ago with no card (numbers or stub)
    now = datetime.now(nr.IST); out = []
    for m in miss:
        try: age = (now - datetime.strptime(m[2], "%d-%b-%Y %H:%M:%S").replace(tzinfo=nr.IST)).total_seconds() / 60
        except Exception: age = 0
        if age >= 60: out.append({"symbol": m[0], "bse": m[1], "filed": m[2], "age_min": round(age), "why": m[3], "text": m[4]})
    json.dump({"asof": now.strftime("%Y-%m-%d %H:%M IST"), "universe": len(seen), "numbers_cards": len(ok), "stub_cards": len(stub), "uncovered": out}, open("state/uncovered.json", "w"), indent=1)
    print("WROTE state/uncovered.json uncovered", len(out), flush=True)
