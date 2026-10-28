"""SME ESM Radar: ONE card for both SME segments, NSE Emerge and BSE SME.
Blocks: snapshot table, today's changes (NSE: effective date from NSE circulars; BSE: latest BSE notice), Stage II now, coming exit milestones
(entry + 90 days; Stage II minimum stay 30 days), stocks that met the 3-month price criteria (price-only test), Stage II watch (PE condition + price level).
A stock listed on both exchanges is shown once with the tag N+B.
PE: NSE quoted PE (NSE API), BSE quoted PE (BSE quote data), filings-derived PE as fallback for NSE. Snapshots are saved to store/sme_eps/pe_snap.json.
Env: OUT (png path), SEND=1 sends the PNG to the PRIVATE results chat only, N500_PE override, PE_FILE (read the PE snapshot instead of fetching), NO_PE_FETCH=1.
Nothing public."""
import os, sys, io, re, json, glob, gzip, csv, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import requests
import theme as T
from theme import BG, PANEL, BORDER, TEXT, MUTED, HEAD, GREEN, RED, AMBER, BLUE
from cards_market import _hdr, _foot
from matplotlib.patches import Rectangle as Rect
OUT = os.environ.get("OUT", "out/esm_radar_sme.png")
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
D = dt.date.fromisoformat
cols = ["d", "src", "isin", "sym", "ser", "o", "h", "l", "c", "pc", "v"]

def short(nm): return re.sub(r"\s+(Limited|Ltd\.?|Private Limited)$", "", re.sub(r"\s+", " ", nm.strip().rstrip("#*")), flags=re.I)

# ---------------------------------------------------------------- prices (adjusted by previous-close chaining), per exchange
def load_prices(tag, sers):
    files = sorted(glob.glob(f"store/prices/d/*_{tag}.csv.gz"))
    df = pd.concat([pd.read_csv(f, names=cols, header=None, dtype={"isin": str, "sym": str}) for f in files[-290:]])
    df["d"] = pd.to_datetime(df["d"])
    for c in ["h", "l", "c", "pc"]: df[c] = pd.to_numeric(df[c], errors="coerce")
    smes = set(df[df["ser"].isin(sers)]["isin"])
    df = df[df["isin"].isin(smes)].sort_values(["isin", "d"]).drop_duplicates(["isin", "d"], keep="last")
    df["lf"] = np.log((df["c"] / df["pc"]).clip(0.2, 5)); df["adj"] = np.exp(df.groupby("isin")["lf"].cumsum()); df["fac"] = df["adj"] / df["c"]
    df["ah"] = df["h"] * df["fac"]; df["al"] = df["l"] * df["fac"]
    A = df.pivot(index="d", columns="isin", values="adj"); H = df.pivot(index="d", columns="isin", values="ah"); L = df.pivot(index="d", columns="isin", values="al"); C = df.pivot(index="d", columns="isin", values="c")
    sym_of = df.drop_duplicates("isin", keep="last").set_index("isin")["sym"].to_dict()
    return dict(A=A, H=H, L=L, C=C, sme=smes, sym=sym_of)
PX = {"N": load_prices("N", ["SM", "ST", "SZ"]), "B": load_prices("B", ["M", "MT", "MS"])}

# ---------------------------------------------------------------- ESM state per exchange
ev_n = sorted(json.load(open("store/esm_history/events.json")), key=lambda e: e["eff"])
DAY = os.environ.get("DAY", "").strip() or max(e["eff"] for e in ev_n); today = D(DAY)
STATE = {"N": {}, "B": {}}; CHG = {"N": collections.defaultdict(list), "B": collections.defaultdict(list)}; ENT_N = {"N": 0, "B": 0}; EXIT_N = {"N": 0, "B": 0}
by = collections.defaultdict(list)
for e in ev_n: by[e["isin"]].append(e)
for i, es in by.items():
    st = ent = s2 = None
    for e in es:
        d = D(e["eff"])
        if d > today: continue
        if e["ev"] == "enter_I": st, ent, s2 = "I", d, None
        elif e["ev"] == "I_to_II": st, s2 = "II", d
        elif e["ev"] == "II_to_I": st, s2 = "I", None
        elif e["ev"] == "exit": st = None
    if st and i in PX["N"]["sme"]: STATE["N"][i] = dict(sym=es[-1]["sym"], name=short(es[-1]["name"]), st=st, ent=ent, s2=s2)
for e in ev_n:
    if e["isin"] not in PX["N"]["sme"]: continue
    if e["eff"] == DAY: CHG["N"][e["ev"]].append(e)
    if 0 <= (today - D(e["eff"])).days <= 7:
        if e["ev"] == "enter_I": ENT_N["N"] += 1
        if e["ev"] == "exit": EXIT_N["N"] += 1
# BSE: current list + events from notice annexures (event date = notice date, effective about the next day)
bl = json.load(open("store/esm/bse_latest.json")); bev = json.load(open("store/esm_history/bse_events.json"))
mc = json.load(open("store/mcap/mcap.json"))
bse_dt = D(f"{bl['notice'][:4]}-{bl['notice'][4:6]}-{bl['notice'][6:8]}")
bby = collections.defaultdict(list)
for e in bev: bby[e["isin"]].append(e)
for i, v in bl["list"].items():
    if not (i in PX["B"]["sme"] or (mc.get(i) or {}).get("g") in ("M", "MT", "MS")): continue
    ent = s2 = None
    for e in sorted(bby.get(i, []), key=lambda e: e["d"]):
        d = D(e["d"]) + dt.timedelta(days=1)
        if e["ev"] == "enter_I": ent, s2 = d, None
        elif e["ev"] == "enter_II": ent, s2 = d, d
        elif e["ev"] == "I_to_II": s2 = d
        elif e["ev"] == "II_to_I": s2 = None
    STATE["B"][i] = dict(sym=v["code"], name=short(v["name"]), st=v["st"], ent=ent, s2=s2)
bsme = set(STATE["B"]) | PX["B"]["sme"]
for e in bev:
    if e["isin"] not in bsme and (mc.get(e["isin"]) or {}).get("g") not in ("M", "MT", "MS"): continue
    if D(e["d"]) == bse_dt: CHG["B"][e["ev"] if e["ev"] != "enter_II" else "I_to_II"].append(e)
    if 0 <= (bse_dt - D(e["d"])).days <= 7:
        if e["ev"] == "enter_I": ENT_N["B"] += 1
        if e["ev"] == "exit": EXIT_N["B"] += 1
name_b = {i: v["name"] for i, v in STATE["B"].items()}
for e in bev: name_b.setdefault(e["isin"], short(e["name"]))

def tag(i):
    n = i in PX["N"]["sme"]; b = i in bsme or i in PX["B"]["sme"]
    return "N+B" if (n and b) else ("NSE" if n else "BSE")
TAGCOL = {"NSE": BLUE, "BSE": AMBER, "N+B": GREEN}
nm_any = lambda i: (STATE["N"].get(i) or {}).get("name") or STATE["B"].get(i, {}).get("name") or name_b.get(i) or PX["N"]["sym"].get(i) or i

# ---------------------------------------------------------------- merged views (a stock listed on both is shown once)
def merged_state():
    out = {}
    for x in ("N", "B"):
        for i, s in STATE[x].items():
            if i in out: continue
            out[i] = dict(s, ex=x, tag=tag(i))
    return out
MS_ = merged_state()
horizon = today + dt.timedelta(days=10); up = []; past = {"N": 0, "B": 0}; nokn = 0
for x in ("N", "B"):
    ref = today if x == "N" else bse_dt
    for i, s in STATE[x].items():
        if x == "B" and i in STATE["N"]: continue
        if s["ent"] is None:
            if s["st"] == "I": nokn += 1
            continue
        if s["st"] == "I":
            d90 = s["ent"] + dt.timedelta(days=90)
            if ref <= d90 <= horizon: up.append((d90, tag(i), s["name"], "Stage I", f"90 days on {d90:%d %b}"))
            elif d90 < ref: past[x] += 1
        if s["st"] == "II" and s["s2"]:
            d30 = s["s2"] + dt.timedelta(days=30)
            if ref <= d30 <= horizon: up.append((d30, tag(i), s["name"], "Stage II", f"30-day min ends {d30:%d %b}"))
up.sort()

# ---------------------------------------------------------------- 3-month Stage I price test (price only), SME stocks not yet in ESM
met = []
for x in ("N", "B"):
    P = PX[x]; A = P["A"]; Hh = P["H"]; Ll = P["L"]; n = 63
    hl = Hh.rolling(n, min_periods=50).max() / Ll.rolling(n, min_periods=50).min() - 1; cc = A / A.shift(n) - 1
    meet = ((hl > .75) & (cc > 0)) | (cc > .5)
    last = A.index[-1]; seen_n = {m[2] for m in met}
    for i in A.columns:
        if i in STATE["N"] or i in STATE["B"]: continue
        if x == "B" and i in PX["N"]["sme"]: continue
        if bool(meet.iloc[-1].get(i, False)):
            k = len(A) - 1
            while k > 0 and bool(meet[i].iloc[k - 1]): k -= 1
            if (last - A.index[k]).days <= 5: met.append((A.index[k], tag(i), i, nm_any(i) if (i in STATE["N"] or i in name_b) else short(nm_any(i))))
met.sort(key=lambda m: m[0], reverse=True)

# ---------------------------------------------------------------- Stage II watch: PE condition (<= 0 or > 2x Nifty 500 PE) + the price level that would meet the price condition
def n500_pe():
    try:
        for back in range(0, 6):
            d = dt.date.today() - dt.timedelta(days=back)
            r = requests.get(f"https://archives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if r.status_code == 200:
                for ln in r.text.splitlines():
                    c = ln.split(",")
                    if c and c[0].strip().lower() == "nifty 500": return float(c[10])
    except Exception: pass
    return None
N500 = float(os.environ["N500_PE"]) if os.environ.get("N500_PE") else n500_pe()
try: eps2 = json.load(open("store/sme_eps/eps2.json"))
except Exception: eps2 = {}
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
def nse_pe_map(syms):
    import time as _t
    out = {}
    try:
        REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
        ss = requests.Session(); ss.headers.update(_UA); ss.get("https://www.nseindia.com/", timeout=25); ss.get(REF, timeout=25)
        for sym in syms:
            for ser in ("ST", "SM", "SZ"):
                try:
                    r = ss.get(f"https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi?functionName=getSymbolData&marketType=N&series={ser}&symbol={sym}", headers={"Referer": REF}, timeout=40)
                    if r.status_code != 200: continue
                    e = r.json().get("equityResponse", [{}])[0]
                    if not e.get("metaData"): continue
                    try: v = float((e.get("secInfo") or {}).get("pdSymbolPe"))
                    except Exception: v = None
                    if v is not None and v > 0: out[sym] = v
                    break
                except Exception: pass
                _t.sleep(0.3)
            _t.sleep(0.4)
    except Exception as ex: print("NSE PE fetch failed:", type(ex).__name__)
    return out
def bse_pe_map(codes, names=None):
    import time as _t, tempfile
    out = {}
    try:
        from bse import BSE
        with BSE(download_folder=tempfile.mkdtemp()) as b:
            for c in codes:
                try:
                    m = b.equityMetaInfo(c)
                    if names is not None and m.get("COName"): names[c] = str(m.get("COName")).strip()
                    for k in ("PE", "ConPE"):
                        try: out[c] = float(str(m.get(k)).replace(",", "")); break
                        except Exception: pass
                except Exception: pass
                _t.sleep(0.3)
    except Exception as ex: print("BSE PE fetch failed:", type(ex).__name__)
    return out
SNAP = {}
W2 = []; pe_na = 0; pe_not_met = 0; pe_src = collections.Counter(); pe_disagree = []
if N500:
    s1 = {i: s for x in ("N", "B") for i, s in STATE[x].items() if s["st"] == "I" and not (x == "B" and i in STATE["N"])}
    if os.environ.get("PE_FILE"): SNAP = json.load(open(os.environ["PE_FILE"]))
    elif os.environ.get("NO_PE_FETCH"): SNAP = {"nse": {}, "bse": {}, "bsen": {}}
    else:
        _bn = {}
        _need = [PX["B"]["sym"].get(m[2]) for m in met if m[1] == "BSE" and PX["B"]["sym"].get(m[2])]
        SNAP = {"d": str(dt.date.today()), "nse": nse_pe_map([s["sym"] for i, s in s1.items() if i in STATE["N"]]), "bse": bse_pe_map([s["sym"] for i, s in s1.items() if i in STATE["B"]] + _need, _bn)}
        SNAP["bsen"] = _bn
        if SNAP["nse"] or SNAP["bse"]:
            os.makedirs("store/sme_eps", exist_ok=True); json.dump(SNAP, open("store/sme_eps/pe_snap.json", "w"))
    for i, s_ in s1.items():
        ex = "N" if i in STATE["N"] else "B"; P = PX[ex]; A = P["A"]; C = P["C"]
        if i not in A.columns: continue
        n_pe = SNAP["nse"].get(s_["sym"]) if ex == "N" else None
        b_pe = SNAP["bse"].get(STATE["B"][i]["sym"]) if i in STATE["B"] else None
        e2 = eps2.get(s_["sym"]) if ex == "N" else None; mine_ok = bool(e2 and e2.get("state") in ("ok", "loss"))
        loss = False
        if n_pe is not None: pe, src = n_pe, "NSE"
        elif b_pe is not None: pe, src = b_pe, "BSE"; loss = b_pe <= 0
        elif mine_ok: pe, src = e2.get("pe"), "filings"; loss = e2["state"] == "loss"
        else: pe_na += 1; continue
        if n_pe is not None and mine_ok and e2.get("pe") and ((n_pe > 2 * N500) != (e2["pe"] > 2 * N500)): pe_disagree.append(s_["name"])
        pe_src[src] += 1
        if not (loss or (pe and pe > 2 * N500)): pe_not_met += 1; continue
        a = A[i].dropna()
        if len(a) < 25: continue
        c_now = float(C[i].dropna().iloc[-1]); fac = c_now / float(a.iloc[-1])
        b5 = float(a.iloc[-5]) * 1.15 * fac; b21 = float(a.iloc[-21]) * 1.30 * fac
        trig = min(b5, b21)
        W2.append((trig / c_now - 1, tag(i), s_["name"], c_now, trig, "loss-making" if loss else f"PE {pe:.0f} ({src})"))
    W2.sort()
    print("PE sources:", dict(pe_src), "| no PE", pe_na, "| not met", pe_not_met, "| NSE vs filings disagree:", pe_disagree)

# ---------------------------------------------------------------- Stage II now
S2 = []
for i, s in MS_.items():
    if s["st"] != "II": continue
    ref = today if s["ex"] == "N" else bse_dt
    S2.append((s["s2"], s["tag"], s["name"], s))
S2.sort(key=lambda r: (r[0] is None, r[0] or dt.date(2000, 1, 1)), reverse=False)
S2 = sorted(S2, key=lambda r: r[0] or dt.date(2000, 1, 1), reverse=True)

# ---------------------------------------------------------------- change lists (merged across exchanges, one row per stock)
CATS = [("enter_I", "Moved into Stage I", AMBER), ("I_to_II", "Stage I to Stage II", RED), ("II_to_I", "Stage II back to Stage I", BLUE), ("exit", "Removed from ESM", GREEN)]
R = []
for k, title, col in CATS:
    seen = {}
    for x in ("N", "B"):
        for e in CHG[x].get(k, []):
            if e["isin"] not in seen: seen[e["isin"]] = (tag(e["isin"]), short(e["name"]))
    if seen: R.append((title, col, sorted(seen.values(), key=lambda r: r[1])))

# ---------------------------------------------------------------- snapshot numbers
def snap(x):
    st = STATE[x]; s1 = sum(1 for s in st.values() if s["st"] == "I"); s2 = sum(1 for s in st.values() if s["st"] == "II")
    return len(st), s1, s2, ENT_N[x], EXIT_N[x], past[x]
SN = {x: snap(x) for x in ("N", "B")}

# ---------------------------------------------------------------- render
W = 10.8; RH = 0.5
UP = up[:12]; MET = met[:10]; W2S = W2[:10]; S2S = S2[:10]
ncell = sum((len(r[2]) + 1) // 2 for r in R)
H_in = (2.7 + 2.6                                              # header + snapshot
        + (0.9 + 0.62 * len(R) + 0.46 * ncell + (0.5 if not R else 0) + 0.3)          # changes
        + (1.5 + RH * max(len(S2S), 1) + 0.45)                  # stage II now
        + (1.5 + RH * max(len(UP), 1) + 0.5)                   # exit milestones
        + (1.5 + RH * max(len(MET), 1) + 0.2)                  # price test
        + (1.6 + RH * max(len(W2S), 1) + 0.5)                  # stage II watch
        + 2.3)
fig = T.new_fig(W, H_in); fx = lambda i: i / W; fy = lambda i: 1 - i / H_in
_hdr(fig, W, H_in, "SME ESM Radar", f"NSE Emerge + BSE SME  |  as of {D(DAY):%d %b %Y}")
def panel(y, h, title, color):
    T.panel(fig, fx(0.45), fy(y + h), (W - 0.9) / W, h / H_in)
    fig.patches.append(Rect((fx(0.45), fy(y + 0.1)), (W - 0.9) / W, 0.1 / H_in, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=5))
    fig.text(fx(0.8), fy(y + 0.5), title, color=color, fontsize=21, fontweight="bold", va="center")
def sub(yy, txt, size=11): fig.text(fx(0.8), fy(yy), txt, color=MUTED, fontsize=size, va="center")
def tg(yy, t, x=0.8): fig.text(fx(x), fy(yy), t, color=TAGCOL[t], fontsize=10.5, fontweight="bold", va="center")
y = 2.7
# snapshot
h = 2.6; panel(y, h, "SNAPSHOT", T.NAVY); yy = y + 1.05
xs = [4.3, 5.5, 6.7, 8.1, 9.5]; heads = ["In ESM", "Stage I", "Stage II", "Entered 7d", "Exited 7d"]
for xx, t in zip(xs, heads): fig.text(fx(xx), fy(yy), t, color=MUTED, fontsize=11.5, ha="right", va="center")
yy += 0.5
for x, lab, col in (("N", "NSE Emerge", BLUE), ("B", "BSE SME", AMBER)):
    s = SN[x]
    fig.text(fx(0.8), fy(yy), lab, color=col, fontsize=15.5, fontweight="bold", va="center")
    for xx, v in zip(xs, s[:5]): fig.text(fx(xx), fy(yy), str(v), color=TEXT, fontsize=15.5, fontweight="bold", ha="right", va="center")
    yy += 0.5
sub(yy + 0.02, f"Nifty 500 PE {N500:.1f} (Stage II PE test: PE at or below 0, or above {2 * N500:.1f}).  Dual-listed stocks count in both rows." if N500 else "Nifty 500 PE unavailable", 10.5)
y += h + 0.25
# today's changes
h1 = 0.9 + 0.62 * len(R) + 0.46 * ncell + (0.5 if not R else 0) + 0.3
panel(y, h1, "TODAY'S CHANGES", T.NAVY); yy = y + 1.05
if not R: fig.text(fx(0.8), fy(yy), "No SME changes today", color=MUTED, fontsize=15, va="center")
for title, col, items in R:
    fig.text(fx(0.8), fy(yy), f"{title} ({len(items)})", color=col, fontsize=15.5, fontweight="bold", va="center"); yy += 0.46
    for k in range(0, len(items), 2):
        for j, (tgx, nm) in enumerate(items[k:k + 2]):
            x0 = 0.9 + j * 4.9
            tg(yy, tgx, x0); fig.text(fx(x0 + 0.75), fy(yy), nm[:26], color=TEXT, fontsize=13.5, va="center")
        yy += 0.46
    yy += 0.16
y += h1 + 0.25
# stage II now
h2 = 1.5 + RH * max(len(S2S), 1) + 0.45
panel(y, h2, "IN STAGE II NOW", RED); yy = y + 1.0
sub(yy, "Trade-for-trade, 2% band, call auction. Stays at least 30 days; back to Stage I if the monthly gain is below 15%."); yy += 0.42
if not S2S: fig.text(fx(0.8), fy(yy), "None", color=MUTED, fontsize=15, va="center")
for s2d, tgx, nm, s in S2S:
    ref = today if s["ex"] == "N" else bse_dt
    tg(yy, tgx); fig.text(fx(1.65), fy(yy), nm[:28], color=TEXT, fontsize=15, fontweight="bold", va="center")
    if s2d: txt = f"since {s2d:%d %b} ({(ref - s2d).days}d)  |  min stay " + ("passed" if ref >= s2d + dt.timedelta(days=30) else f"ends {s2d + dt.timedelta(days=30):%d %b}")
    else: txt = "Stage II before our records began"
    fig.text(fx(W - 0.8), fy(yy), txt, color=HEAD, fontsize=12.5, ha="right", va="center"); yy += RH
if len(S2) > len(S2S): sub(yy, f"+{len(S2) - len(S2S)} more in Stage II")
y += h2 + 0.25
# exit milestones
h3 = 1.5 + RH * max(len(UP), 1) + 0.5
panel(y, h3, "COMING UP: EXIT MILESTONES (10 days)", GREEN); yy = y + 1.0
sub(yy, "Earliest eligible date; the exchange usually acts a few days later (typically 95-98 days after entry)."); yy += 0.42
if not UP: fig.text(fx(0.8), fy(yy), "None in the next 10 days", color=MUTED, fontsize=15, va="center")
for d, tgx, nm, st, txt in UP:
    tg(yy, tgx); fig.text(fx(1.65), fy(yy), nm[:28], color=TEXT, fontsize=15, fontweight="bold", va="center")
    fig.text(fx(W - 0.8), fy(yy), f"{st}: {txt}", color=HEAD, fontsize=13, ha="right", va="center"); yy += RH
ex = (f"+{len(up) - len(UP)} more.  " if len(up) > len(UP) else "") + f"Past 90 days and still listed: NSE {past['N']}, BSE {past['B']}" + (f" (BSE history starts Jul 2025; entry date unknown for {nokn} Stage I stocks)." if nokn else ".")
sub(yy, ex)
y += h3 + 0.25
# price test
h4 = 1.5 + RH * max(len(MET), 1) + 0.2
panel(y, h4, "MET STAGE I PRICE TEST (3-month)", AMBER); yy = y + 1.0
sub(yy, "Price-only test on SME stocks not in ESM. In past tests about 3 in 10 such stocks were added within 3 trading days."); yy += 0.42
if not MET: fig.text(fx(0.8), fy(yy), "No SME stock newly meets the test", color=MUTED, fontsize=15, va="center")
for d, tgx, i, nm in MET:
    if nm == i or re.match(r"^INE", nm): nm = short((SNAP.get("bsen") or {}).get(PX["B"]["sym"].get(i), "")) or f"BSE {PX['B']['sym'].get(i, i)}"
    tg(yy, tgx); fig.text(fx(1.65), fy(yy), nm[:30], color=TEXT, fontsize=15, fontweight="bold", va="center")
    fig.text(fx(W - 0.8), fy(yy), f"first met {d:%d %b}", color=HEAD, fontsize=13, ha="right", va="center"); yy += RH
y += h4 + 0.25
# stage II watch
h5 = 1.6 + RH * max(len(W2S), 1) + 0.5
panel(y, h5, "STAGE II WATCH (price + PE)", RED); yy = y + 1.0
sub(yy, f"Stage I stocks whose PE condition is met (loss-making or PE above {2 * N500:.1f}). Price levels are for the next close." if N500 else "Nifty 500 PE unavailable"); yy += 0.42
if not W2S: fig.text(fx(0.8), fy(yy), "No Stage I SME stock currently meets the PE condition with PE data", color=MUTED, fontsize=14, va="center")
for gap, tgx, nm, c_now, trig, pe_t in W2S:
    tg(yy, tgx); fig.text(fx(1.65), fy(yy), nm[:24], color=TEXT, fontsize=15, fontweight="bold", va="center")
    lvl = f"price test met at last close (Rs {c_now:,.2f})" if gap <= 0 else f"close above Rs {trig:,.2f} (+{gap * 100:.1f}%)"
    fig.text(fx(W - 0.8), fy(yy), f"{lvl}  |  {pe_t}", color=HEAD, fontsize=12, ha="right", va="center"); yy += RH
sub(yy, f"{pe_na} Stage I stocks have no usable PE; {pe_not_met} do not meet the PE condition." if N500 else "")
_foot(fig, W, H_in, f"NSE as of {D(DAY):%d %b}, BSE notice {bse_dt:%d %b} (BSE effect about next day). N+B = listed on both. PE: exchange-quoted. Not a forecast. For educational purpose only. Not an investment advice.")
T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
T.save(fig, OUT)
print("saved", OUT, "| NSE", SN["N"], "| BSE", SN["B"], "| changes", {k: len(v) for k, v in CHG["N"].items()}, {k: len(v) for k, v in CHG["B"].items()}, "| stageII", len(S2), "| upcoming", len(up), "| met", len(met), "| watch", len(W2))
if os.environ.get("SEND") == "1":
    tok = os.environ["TELEGRAM_BOT_TOKEN"].strip(); chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    with open(OUT, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat, "caption": "SME ESM Radar (dry run, private)"}, files={"photo": fh}, timeout=60)
    print("sent private ok=", r.json().get("ok"))
