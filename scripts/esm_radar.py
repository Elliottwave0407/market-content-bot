"""SME ESM Radar: ONE card for the NSE Emerge (SME) segment. Blocks: today's changes (exact, from NSE circulars), coming exit milestones
(entry + 90 days; Stage II minimum stay 30 days), and stocks that met the 3-month price criteria (price-only test, hit rate shown).
Env: OUT (png path), SEND=1 sends the PNG to the PRIVATE results chat only. Nothing public."""
import os, sys, io, json, glob, gzip, csv, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import theme as T
from theme import BG, PANEL, BORDER, TEXT, MUTED, HEAD, GREEN, RED, AMBER, BLUE
from cards_market import _hdr, _foot
from matplotlib.patches import Rectangle as Rect
OUT = os.environ.get("OUT", "out/esm_radar_sme.png")
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
D = dt.date.fromisoformat
cols = ["d", "src", "isin", "sym", "ser", "o", "h", "l", "c", "pc", "v"]
files = sorted(glob.glob("store/prices/d/*_N.csv.gz"))
df = pd.concat([pd.read_csv(f, names=cols, header=None, dtype={"isin": str}) for f in files[-290:]])
df["d"] = pd.to_datetime(df["d"])
for c in ["h", "l", "c", "pc"]: df[c] = pd.to_numeric(df[c], errors="coerce")
sme = set(df[df.ser.isin(["SM", "ST", "SZ"])].isin_ if False else df[df["ser"].isin(["SM", "ST", "SZ"])]["isin"])
df = df.sort_values(["isin", "d"]).drop_duplicates(["isin", "d"], keep="last")
df["lf"] = np.log((df["c"] / df["pc"]).clip(0.2, 5)); df["adj"] = np.exp(df.groupby("isin")["lf"].cumsum()); df["fac"] = df["adj"] / df["c"]
df["ah"] = df["h"] * df["fac"]; df["al"] = df["l"] * df["fac"]
ev = sorted(json.load(open("store/esm_history/events.json")), key=lambda e: e["eff"])
DAY = os.environ.get("DAY", "").strip() or max(e["eff"] for e in ev); today = D(DAY)
by = collections.defaultdict(list)
for e in ev: by[e["isin"]].append(e)
state = {}
for i, es in by.items():
    st = ent = s2 = None
    for e in es:
        d = D(e["eff"])
        if d > today: continue
        if e["ev"] == "enter_I": st, ent, s2 = "I", d, None
        elif e["ev"] == "I_to_II": st, s2 = "II", d
        elif e["ev"] == "II_to_I": st, s2 = "I", None
        elif e["ev"] == "exit": st = None
    if st and i in sme: state[i] = dict(sym=es[-1]["sym"], name=es[-1]["name"], st=st, ent=ent, s2=s2)
chg = collections.defaultdict(list)
for e in ev:
    if e["eff"] == DAY and e["isin"] in sme: chg[e["ev"]].append(e)
# coming milestones
import re
def short(nm): return re.sub(r"\s+(Limited|Ltd\.?|Private Limited)$", "", re.sub(r"\s+", " ", nm.strip()), flags=re.I)
horizon = today + dt.timedelta(days=10); up = []; past = 0
for i, s in state.items():
    d90 = s["ent"] + dt.timedelta(days=90)
    if s["st"] == "I":
        if today <= d90 <= horizon: up.append((d90, short(s["name"]), "Stage I", f"90 days on {d90:%d %b}"))
        elif d90 < today: past += 1
    if s["st"] == "II":
        d30 = s["s2"] + dt.timedelta(days=30)
        if today <= d30 <= horizon: up.append((d30, short(s["name"]), "Stage II", f"30-day minimum ends {d30:%d %b}"))
up.sort()
# 3-month criteria (price only, NSE SME not in ESM)
A = df.pivot(index="d", columns="isin", values="adj"); H = df.pivot(index="d", columns="isin", values="ah"); L = df.pivot(index="d", columns="isin", values="al"); C = df.pivot(index="d", columns="isin", values="c")
n = 63
hl = H.rolling(n, min_periods=50).max() / L.rolling(n, min_periods=50).min() - 1; cc = A / A.shift(n) - 1
meet = ((hl > .75) & (cc > 0)) | (cc > .5)
last = A.index[-1]; meet_l = meet.iloc[-1]; prev_l = meet.iloc[-2] if len(A) > 1 else meet_l
watch = []
for i in A.columns:
    if i not in sme or i in state: continue
    if bool(meet_l.get(i, False)):
        first = last
        k = len(A) - 1
        while k > 0 and bool(meet[i].iloc[k - 1]): k -= 1
        watch.append((A.index[k], by[i][-1]["name"] if i in by else df[df.isin_ == i].sym.iloc[-1] if False else i, i))
sym_of = df.drop_duplicates("isin", keep="last").set_index("isin")["sym"].to_dict()
name_of = {i: (short(by[i][-1]["name"]) if i in by else sym_of.get(i, i)) for i in A.columns}
met = sorted([(d, name_of[i]) for d, _, i in watch if (last - d).days <= 5], key=lambda x: x[0], reverse=True)


# ---- Stage II watch: Stage I SME stocks whose PE condition is met (loss-making or PE > 2x Nifty 500 PE) and the close that would meet the price condition
def n500_pe():
    try:
        r = requests.get(f"https://archives.nseindia.com/content/indices/ind_close_all_{dt.date.today():%d%m%Y}.csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code != 200:
            for back in range(1, 6):
                d = dt.date.today() - dt.timedelta(days=back)
                r = requests.get(f"https://archives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                if r.status_code == 200: break
        for ln in r.text.splitlines():
            c = ln.split(",")
            if c and c[0].strip().lower() == "nifty 500": return float(c[10])
    except Exception:
        pass
    return None
import requests
N500 = float(os.environ["N500_PE"]) if os.environ.get("N500_PE") else n500_pe()
try: eps2 = json.load(open("store/sme_eps/eps2.json"))
except Exception: eps2 = {}
W2 = []; pe_na = 0; pe_not_met = 0
if N500:
    for i, s_ in state.items():
        if s_["st"] != "I" or i not in A.columns: continue
        e2 = eps2.get(s_["sym"])
        if not e2 or e2.get("state") not in ("ok", "loss"): pe_na += 1; continue
        pe = e2.get("pe"); loss = e2["state"] == "loss"
        if not (loss or (pe and pe > 2 * N500)): pe_not_met += 1; continue
        a = A[i].dropna()
        if len(a) < 25: continue
        c_now = float(C[i].dropna().iloc[-1]); fac = c_now / float(a.iloc[-1])
        b5 = float(a.iloc[-5]) * 1.15 * fac     # next close vs the close 4 trading days back (the window moves one day)
        b21 = float(a.iloc[-21]) * 1.30 * fac
        trig = min(b5, b21); which = "5-day +15%" if b5 <= b21 else "month +30%"
        W2.append((trig / c_now - 1, s_["name"], c_now, trig, which, "loss-making" if loss else f"PE {pe:.0f}"))
    W2.sort()

def block_rows():
    rows = []
    for k, title, col in [("enter_I", "Moved into Stage I", AMBER), ("I_to_II", "Stage I to Stage II", RED), ("II_to_I", "Stage II back to Stage I", BLUE), ("exit", "Removed from ESM", GREEN)]:
        g = sorted(chg.get(k, []), key=lambda e: e["name"])
        if g: rows.append((title, col, [e["name"] for e in g]))
    return rows
R = block_rows()
W = 10.8; RH = 0.52
nch = sum(len(r[2]) for r in R) + (0 if R else 1)
UP = up[:12]; MET = met[:8]; W2S = W2[:8]
H_in = 2.7 + (0.9 + 0.75 * len(R) + RH * nch) + (1.2 + RH * max(len(UP), 1) + 0.4) + (1.5 + RH * max(len(MET), 1)) + (1.5 + RH * max(len(W2S), 1) + 0.4) + 2.0
fig = T.new_fig(W, H_in); fx = lambda i: i / W; fy = lambda i: 1 - i / H_in
_hdr(fig, W, H_in, "SME ESM Radar", f"NSE Emerge  |  effective {D(DAY):%d %b %Y}  |  {len(state)} SME stocks in ESM")
def panel(y, h, title, color):
    T.panel(fig, fx(0.45), fy(y + h), (W - 0.9) / W, h / H_in)
    fig.patches.append(Rect((fx(0.45), fy(y + 0.1)), (W - 0.9) / W, 0.1 / H_in, transform=fig.transFigure, facecolor=color, edgecolor="none", zorder=5))
    fig.text(fx(0.8), fy(y + 0.5), title, color=color, fontsize=22, fontweight="bold", va="center")
y = 2.7
h1 = 0.9 + 0.75 * len(R) + RH * nch
panel(y, h1, "TODAY'S CHANGES", T.NAVY); yy = y + 1.05
if not R: fig.text(fx(0.8), fy(yy), "No SME changes effective today", color=MUTED, fontsize=16, va="center")
for title, col, names in R:
    fig.text(fx(0.8), fy(yy), f"{title} ({len(names)})", color=col, fontsize=16, fontweight="bold", va="center"); yy += 0.5
    for nm in names:
        fig.text(fx(1.0), fy(yy), short(nm)[:46], color=TEXT, fontsize=15.5, va="center"); yy += RH
    yy += 0.25 - 0.0
y += h1 + 0.25
h2 = 1.2 + RH * max(len(UP), 1) + 0.4
panel(y, h2, "COMING UP: EXIT MILESTONES (next 10 days)", GREEN); yy = y + 1.0
fig.text(fx(0.8), fy(yy), "Earliest eligible date, NSE usually acts a few days later (typically 95-98 days after entry)", color=MUTED, fontsize=11.5, va="center"); yy += 0.42
if not UP: fig.text(fx(0.8), fy(yy), "None in the next 10 days", color=MUTED, fontsize=15, va="center")
for d, nm, st, txt in UP:
    fig.text(fx(0.8), fy(yy), nm[:34], color=TEXT, fontsize=15.5, fontweight="bold", va="center")
    fig.text(fx(W - 0.8), fy(yy), f"{st}: {txt}", color=HEAD, fontsize=13, ha="right", va="center"); yy += RH
extra = (f"+{len(up) - 12} more.  " if len(up) > 12 else "") + (f"{past} Stage I stocks are already past 90 days and still listed." if past else "")
if extra: fig.text(fx(0.8), fy(yy), extra, color=MUTED, fontsize=11.5, va="center")
y += h2 + 0.25
h3 = 1.5 + RH * max(len(MET), 1)
panel(y, h3, "MET STAGE I PRICE TEST (3-month)", AMBER); yy = y + 1.0
fig.text(fx(0.8), fy(yy), "Price-only test. In past tests about 3 in 10 such stocks were added within 3 trading days.", color=MUTED, fontsize=11.5, va="center"); yy += 0.42
if not MET: fig.text(fx(0.8), fy(yy), "No SME stock newly meets the test", color=MUTED, fontsize=15, va="center")
for d, nm in MET:
    fig.text(fx(0.8), fy(yy), nm[:34], color=TEXT, fontsize=15.5, fontweight="bold", va="center")
    fig.text(fx(W - 0.8), fy(yy), f"first met {d:%d %b}", color=HEAD, fontsize=13, ha="right", va="center"); yy += RH
y += h3 + 0.25
h4 = 1.5 + RH * max(len(W2S), 1) + 0.4
panel(y, h4, "STAGE II WATCH (price + PE)", RED); yy = y + 1.0
fig.text(fx(0.8), fy(yy), f"Stage I stocks whose PE condition is met (loss-making or PE above 2x Nifty 500 PE, now {2 * N500:.1f}). Price levels are for the next close." if N500 else "Nifty 500 PE unavailable", color=MUTED, fontsize=11, va="center"); yy += 0.42
if not W2S: fig.text(fx(0.8), fy(yy), "No Stage I SME stock currently meets the PE condition with PE data on file", color=MUTED, fontsize=14, va="center")
for gap, nm, c_now, trig, which, pe_t in W2S:
    fig.text(fx(0.8), fy(yy), short(nm)[:26], color=TEXT, fontsize=15.5, fontweight="bold", va="center")
    fig.text(fx(W - 0.8), fy(yy), f"close above Rs {trig:,.2f} ({gap * 100:+.1f}%)  |  {pe_t}", color=HEAD, fontsize=12.5, ha="right", va="center"); yy += RH
note = f"{pe_na} Stage I SME stocks have no usable PE on file (scanned or stale filings) and {pe_not_met} do not meet the PE condition." if N500 else ""
fig.text(fx(0.8), fy(yy), note, color=MUTED, fontsize=11, va="center")
_foot(fig, W, H_in, "Source: NSE surveillance circulars and NSE daily prices. Exit dates follow the 90-day / 30-day rules; price tests and PE (from filings) are not a forecast. NSE Emerge only. For educational purpose only. Not an investment advice.")
T.brand(fig, h_in=1.15, x_right=fx(W - 0.75), top=fy(0.62))
T.save(fig, OUT)
print("saved", OUT, "| changes", {k: len(v) for k, v in chg.items()}, "| upcoming", len(up), "| met", len(met), "| SME in ESM", len(state))
if os.environ.get("SEND") == "1":
    import requests
    tok = os.environ["TELEGRAM_BOT_TOKEN"].strip(); chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    with open(OUT, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat, "caption": "SME ESM Radar (dry run, private)"}, files={"photo": fh}, timeout=60)
    print("sent private ok=", r.json().get("ok"))
