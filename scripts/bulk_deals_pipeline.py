import re
import csv
import io
import sys
import json
import requests
from datetime import datetime
from bse import BSE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
NSE_LISTS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv",
]
GROUPS = ["A", "B", "IP", "M", "MS", "MT", "P", "R", "T", "TS", "X", "XT", "Y", "Z", "ZP"]

def norm(s):
    s = re.sub(r"[^A-Z0-9]", "", s.upper())
    return re.sub(r"(LIMITED|LTD|L)$", "", s)

def nse_rows():
    r = requests.get("https://nsearchives.nseindia.com/content/equities/bulk.csv", headers=UA, timeout=20)
    out = []
    for x in csv.DictReader(io.StringIO(r.text)):
        if not x.get("Symbol"):
            continue
        out.append({
            "ex": "N",
            "date": datetime.strptime(x["Date"], "%d-%b-%Y"),
            "sym": x["Symbol"].strip(),
            "name": x["Security Name"].strip(),
            "client": x["Client Name"].strip(),
            "side": "B" if x["Buy/Sell"].strip().upper() == "BUY" else "S",
            "qty": float(x["Quantity Traded"]),
            "price": float(x["Trade Price / Wght. Avg. Price"]),
        })
    return out

def bse_rows(bse, day):
    ds = day.strftime("%d/%m/%Y")
    url = f"{bse.api_url}/BulkblockDeal/w?fromdt={ds}&todt={ds}&type=&scripcode="
    data = bse.session.get(url, timeout=15).json().get("Table", [])
    return [{
        "ex": "B",
        "date": day,
        "sym": "",
        "code": str(x["SCRIP_CODE"]),
        "name": x["scripname"],
        "client": x["CLIENT_NAME"].strip(),
        "side": x["TRANSACTION_TYPE"],
        "qty": float(x["QUANTITY"]),
        "price": float(x["PRICE"]),
    } for x in data]

def nse_isins():
    out = {}
    for u in NSE_LISTS:
        r = requests.get(u, headers=UA, timeout=20)
        for x in csv.DictReader(io.StringIO(r.text)):
            x = {k.strip(): (v or "").strip() for k, v in x.items() if k}
            out[x.get("SYMBOL")] = x.get("ISIN NUMBER")
    return out

def bse_universe(bse):
    recs = []
    for g in GROUPS:
        recs += bse.listSecurities(group=g)
    return recs

def resolve(rows, recs, isins):
    by_id = {r["scrip_id"].upper(): r for r in recs if r.get("scrip_id")}
    by_isin = {r["ISIN_NUMBER"]: r for r in recs if r.get("ISIN_NUMBER")}
    by_code = {r["SCRIP_CD"]: r for r in recs}
    by_name = {}
    for r in recs:
        by_name[norm(r.get("Issuer_Name") or "")] = r
        by_name[norm(r.get("Scrip_Name") or "")] = r
    for x in rows:
        if x["ex"] == "B":
            x["rec"] = by_code.get(x["code"])
            x["key"] = x["code"]
        else:
            x["rec"] = by_id.get(x["sym"].upper()) or by_isin.get(isins.get(x["sym"])) or by_name.get(norm(x["name"]))
            x["key"] = x["rec"]["SCRIP_CD"] if x["rec"] else "N:" + x["sym"]

def net_deals(rows):
    tot = {}
    for x in rows:
        t = tot.setdefault((x["client"], x["key"]), {"B": 0.0, "S": 0.0})
        t[x["side"]] += x["qty"]
    cross = set()
    for k, t in tot.items():
        if min(t["B"], t["S"]) > 0 and abs(t["B"] - t["S"]) < 0.1 * max(t["B"], t["S"]):
            cross.add(k)
    sides = {}
    for x in rows:
        sides.setdefault((x["ex"], x["client"], x["key"]), set()).add(x["side"])
    algo = {}
    for (ex, client, key), s in sides.items():
        if len(s) == 2:
            algo.setdefault((ex, client), set()).add(key)
    agg = {}
    for x in rows:
        if (x["client"], x["key"]) in cross or len(algo.get((x["ex"], x["client"]), ())) >= 2:
            continue
        a = agg.setdefault((x["ex"], x["key"], x["client"]), {"B": [0.0, 0.0], "S": [0.0, 0.0], "x": x})
        a[x["side"]][0] += x["qty"]
        a[x["side"]][1] += x["qty"] * x["price"]
    kept = []
    for (ex, key, client), a in agg.items():
        net = a["B"][0] - a["S"][0]
        if abs(net) < 0.1 * max(a["B"][0], a["S"][0]):
            continue
        side = "B" if net > 0 else "S"
        avg = a[side][1] / a[side][0]
        cr = abs(net) * avg / 1e7
        if cr < 0.1:
            continue
        kept.append({"ex": ex, "key": key, "name": a["x"]["name"], "rec": a["x"]["rec"], "client": client, "side": side, "qty": abs(net), "price": round(avg, 2), "cr": cr})
    return kept

def enrich(bse, kept):
    ltp = {}
    for x in kept:
        x["mcap"] = None
        x["stake"] = None
        rec = x["rec"]
        if not rec:
            continue
        code = rec["SCRIP_CD"]
        if code not in ltp:
            try:
                ltp[code] = float(bse.quote(int(code))["LTP"])
            except Exception:
                ltp[code] = None
        try:
            mc = float(str(rec["Mktcap"]).replace(",", ""))
        except Exception:
            continue
        if mc <= 0:
            continue
        x["mcap"] = mc
        if ltp[code]:
            x["stake"] = x["qty"] / (mc * 1e7 / ltp[code]) * 100

def main():
    n = nse_rows()
    if not n:
        print("No NSE rows")
        return
    day = n[0]["date"]
    with BSE(download_folder='./') as bse:
        rows = n + bse_rows(bse, day)
        recs = bse_universe(bse)
        resolve(rows, recs, nse_isins())
        kept = net_deals(rows)
        enrich(bse, kept)
    miss = sorted(set(x["name"] for x in kept if x["ex"] == "N" and not x["rec"]))
    print(f"Day: {day:%d-%b-%Y} | raw: {len(rows)} | kept: {len(kept)} | BSE universe: {len(recs)}")
    print("Unmapped NSE stocks:", miss)
    kept.sort(key=lambda x: x["mcap"] or 0, reverse=True)
    for x in kept:
        mc = f"{x['mcap']:,.0f}" if x["mcap"] else "NA"
        st = f"{x['stake']:.2f}" if x["stake"] is not None else "NA"
        print(f"{x['ex']} | {x['name'][:22]} | {x['client'][:28]} | {x['side']} | {x['qty']:,.0f} @ {x['price']} | {x['cr']:.1f} | {st}% | {mc}")
    with open("debug-bulk-deals-output.json", "w") as f:
        json.dump([{k: v for k, v in x.items() if k != "rec"} for x in kept], f, indent=2)
    print("\nDone.")

try:
    main()
except Exception as e:
    print(f"\nCaught error: {e}")

sys.exit(0)
