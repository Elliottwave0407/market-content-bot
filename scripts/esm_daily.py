"""ESM daily change digest (NSE) from store/esm_history/events.json. Text message to the PRIVATE results chat only; dry run unless SEND=1.
Env: DAY (YYYY-MM-DD effective date; default = latest effective date in the table), SEND."""
import os, sys, json, requests
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
ev = json.load(open("store/esm_history/events.json"))
day = os.environ.get("DAY", "").strip() or max(e["eff"] for e in ev)
by = {}
for e in sorted(ev, key=lambda x: x["eff"]): by.setdefault(e["isin"], []).append(e)
def days_in(e):
    """calendar days since this stock last entered ESM (before e)"""
    start = None
    for x in by[e["isin"]]:
        if x["eff"] > e["eff"] or (x["eff"] == e["eff"] and x is e): break
        if x["ev"] == "enter_I": start = x["eff"]
    return (datetime.fromisoformat(e["eff"]) - datetime.fromisoformat(start)).days if start else None
def nxt(e):
    n = [x for x in by[e["isin"]] if x["eff"] < e["eff"] and x["ev"] == "exit"]
    return len([x for x in by[e["isin"]] if x["ev"] == "enter_I" and x["eff"] < e["eff"]])
today = [e for e in ev if e["eff"] == day]
groups = [("enter_I", "➡️ Moved into ESM Stage I"), ("I_to_II", "⬆️ Stage I to Stage II"), ("II_to_I", "⬇️ Stage II back to Stage I"), ("exit", "✅ Removed from ESM")]
d = datetime.fromisoformat(day)
lines = [f"📋 NSE ESM changes, effective {d:%d %b %Y}", ""]
for k, title in groups:
    g = [e for e in today if e["ev"] == k]
    if not g: continue
    lines.append(f"{title} ({len(g)})")
    for e in sorted(g, key=lambda x: x["name"]):
        extra = ""
        if k != "enter_I":
            n = days_in(e)
            if n is not None: extra = f" · {n} days since entering ESM"
        else:
            c = nxt(e)
            if c: extra = f" · re-entry (earlier entries: {c})"
        lines.append(f"• {e['name']} ({e['sym']}){extra}")
    lines.append("")
lines.append("Source: NSE surveillance circulars. Stage I: 100% margin, trade-for-trade, 5% price band. Stage II: 100% margin, 2% price band, periodic call auction.")
lines.append("For educational purpose only. Not an investment advice.")
txt = "\n".join(lines)
p("events for", day, ":", len(today))
for l in lines: p(l[:200])
if os.environ.get("SEND") == "1" and today:
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN'].strip()}/sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"].strip(), "text": txt[:4000]}, timeout=30)
    p("sent private ok=", r.json().get("ok"))
publish()
