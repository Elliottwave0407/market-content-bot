import requests
import csv
import io
import sys
import json
from datetime import datetime
from bse import BSE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def nse_rows():
    r = requests.get("https://nsearchives.nseindia.com/content/equities/bulk.csv", headers=UA, timeout=20)
    out = []
    for x in csv.DictReader(io.StringIO(r.text)):
        if not x.get("Symbol"):
            continue
        out.append({
            "ex": "N",
            "date": datetime.strptime(x["Date"], "%d-%b-%Y"),
            "name": x["Security Name"].strip(),
            "client": x["Client Name"].strip(),
            "side": "B" if x["Buy/Sell"].strip().upper() == "BUY" else "S",
            "qty": float(x["Quantity Traded"]),
            "price": float(x["Trade Price / Wght. Avg. Price"]),
        })
    return out

def bse_rows(day):
    with BSE(download_folder='./') as bse:
        ds = day.strftime("%d/%m/%Y")
        url = f"{bse.api_url}/BulkblockDeal/w?fromdt={ds}&todt={ds}&type=&scripcode="
        data = bse.session.get(url, timeout=15).json().get("Table", [])
    return [{
        "ex": "B",
        "date": day,
        "name": x["scripname"],
        "client": x["CLIENT_NAME"].strip(),
        "side": x["TRANSACTION_TYPE"],
        "qty": float(x["QUANTITY"]),
        "price": float(x["PRICE"]),
    } for x in data]

def net_deals(rows):
    sides = {}
    for x in rows:
        sides.setdefault((x["ex"], x["client"], x["name"]), set()).add(x["side"])
    algo = {}
    for (ex, client, name), s in sides.items():
        if len(s) == 2:
            algo.setdefault((ex, client), set()).add(name)
    agg = {}
    for x in rows:
        a = agg.setdefault((x["ex"], x["name"], x["client"]), {"B": [0.0, 0.0], "S": [0.0, 0.0]})
        a[x["side"]][0] += x["qty"]
        a[x["side"]][1] += x["qty"] * x["price"]
    kept = []
    dropped = {"algo": 0, "roundtrip": 0}
    for (ex, name, client), a in agg.items():
        if len(algo.get((ex, client), ())) >= 2:
            dropped["algo"] += 1
            continue
        net = a["B"][0] - a["S"][0]
        big = max(a["B"][0], a["S"][0])
        if abs(net) < 0.1 * big:
            dropped["roundtrip"] += 1
            continue
        side = "B" if net > 0 else "S"
        avg = a[side][1] / a[side][0]
        kept.append({"ex": ex, "name": name, "client": client, "side": side, "qty": abs(net), "price": round(avg, 2), "cr": abs(net) * avg / 1e7})
    return kept, dropped

def main():
    n = nse_rows()
    if not n:
        print("No NSE rows")
        return
    day = n[0]["date"]
    rows = n + bse_rows(day)
    kept, dropped = net_deals(rows)
    print(f"Day: {day:%d-%b-%Y} | raw: {len(rows)} | kept: {len(kept)} | dropped: {dropped}")
    for ex in ("N", "B"):
        sel = sorted([x for x in kept if x["ex"] == ex], key=lambda x: x["cr"], reverse=True)
        print(f"\nExchange {ex}: {len(sel)} deals")
        for x in sel:
            print(f"{x['name']} | {x['client']} | {x['side']} | {x['qty']:,.0f} @ {x['price']} = {x['cr']:.1f}")
    with open("debug-bulk-deals-output.json", "w") as f:
        json.dump(kept, f, indent=2)
    print("\nDone.")

try:
    main()
except Exception as e:
    print(f"\nCaught error: {e}")

sys.exit(0)
