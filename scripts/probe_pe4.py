import os, sys, json, time, re, glob, gzip, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
REF = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
try:
    ev = sorted(json.load(open("store/esm_history/events.json")), key=lambda e: e["eff"])
    st = {}
    for e in ev: st[e["isin"]] = (e["sym"], {"enter_I": "I", "I_to_II": "II", "II_to_I": "I", "exit": None}[e["ev"]])
    syms = [v[0] for k, v in st.items() if v[1]]
    last = sorted(glob.glob("store/prices/d/*_N.csv.gz"))[-1]
    sme = {r[3] for r in csv.reader(gzip.open(last, "rt")) if r[4] in ("SM", "ST", "SZ")}
    pick = [x for x in syms if x in sme][:6]
    p("sme in esm picked:", pick)
    s = requests.Session(); s.headers.update(UA); s.get("https://www.nseindia.com/", timeout=25); s.get(REF, timeout=25)
    first = True
    for sym in pick:
        for per in ["Half-Yearly", "Annual", "Quarterly"]:
            r = s.get(f"https://www.nseindia.com/api/corporates-financial-results?index=sme&symbol={sym}&period={per}", headers={"Referer": REF}, timeout=40)
            try: j = r.json()
            except Exception: j = []
            p(sym, per, r.status_code, "records", len(j), [(x.get("toDate"), x.get("filingDate", "")[:11], x.get("consolidated")) for x in j[:3]])
            if j and first:
                first = False; p("fields:", list(j[0].keys())); p("record:", json.dumps(j[0])[:900])
                xb = j[0].get("xbrl")
                if xb and str(xb).startswith("http"):
                    x = requests.get(xb, headers=UA, timeout=40); p("xbrl", x.status_code, len(x.text))
                    t = x.text
                    for tag in ["EarningsPerShare", "BasicEarningsLossPerShare", "ProfitLoss", "DateOfEndOfReportingPeriod"]:
                        m = re.findall(r"<[^>]*" + tag + r"[^>]*>([^<]*)<", t)[:4]; p(tag, m)
            time.sleep(0.8)
except Exception as e:
    import traceback; p("ERR", traceback.format_exc()[-500:])
publish()
