"""BSE scrip code -> hashtag symbol map (NSE symbol if the ISIN trades on NSE, else the BSE ticker). Writes state/symbols.json (tickers only)."""
import os, io, csv, json, zipfile, tempfile, sys
from datetime import datetime, timedelta
import requests
sys.path.insert(0, os.path.dirname(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
OUT = "state/symbols.json"

def main():
    from bse import BSE
    s = requests.Session()
    nse_isin_sym, day = {}, None
    for back in range(0, 8):
        d = datetime.now() - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        r = s.get(f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", headers=UA, timeout=60)
        if r.status_code != 200:
            continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for x in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore"))):
            if x["SctySrs"].strip() in ("EQ", "BE", "SM", "ST", "BZ") and x["ISIN"].strip():
                nse_isin_sym[x["ISIN"].strip()] = x["TckrSymb"].strip()
        day = d
        break
    if not day:
        print("no NSE file"); return
    m = {}
    tmp = tempfile.mkdtemp()
    with BSE(download_folder=tmp) as b:
        for back in range(0, 8):
            d = day - timedelta(days=back)
            try:
                path = b.bhavcopyReport(d, tmp)
            except Exception:
                continue
            for x in csv.DictReader(open(path, encoding="utf-8", errors="ignore")):
                code, isin, tk = x["FinInstrmId"].strip(), x["ISIN"].strip(), x["TckrSymb"].strip()
                m[code] = nse_isin_sym.get(isin) or tk
            break
    old = {}
    try:
        old = json.load(open(OUT)).get("m", {})
    except Exception:
        pass
    old.update({k: v for k, v in m.items() if v})      # keep older codes (delisted/suspended still appear in old filings)
    os.makedirs("state", exist_ok=True)
    json.dump({"asof": f"{day:%Y-%m-%d}", "m": old}, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
    print("symbols:", len(old), "from NSE ISIN match:", sum(1 for v in m.values() if v in set(nse_isin_sym.values())))

if __name__ == "__main__":
    main()
