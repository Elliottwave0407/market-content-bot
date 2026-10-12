import requests, sys, json, re
from ci_out import p, publish
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36", "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}

def t(name, fn):
    try:
        fn()
    except Exception as e:
        p(name, "ERROR", repr(e)[:300])

def nse_api():
    s = requests.Session(); s.headers.update(UA)
    r0 = s.get("https://www.nseindia.com/reports/fii-dii", timeout=20)
    p("nse warmup", r0.status_code, list(s.cookies.keys()))
    r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", headers={"Referer": "https://www.nseindia.com/reports/fii-dii"}, timeout=20)
    p("fiidiiTradeReact", r.status_code, r.text[:800])

def nse_csv(u):
    def f():
        r = requests.get(u, headers=UA, timeout=20)
        p(u.split("/")[-1], r.status_code, len(r.text)); p(r.text[:500].replace("\n", " // "))
    return f

def fivepaisa():
    r = requests.get("https://www.5paisa.com/share-market-today/fii-dii-data", headers=UA, timeout=20)
    p("5paisa", r.status_code, len(r.text))
    txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
    for m in re.finditer(r"(Buy|Gross)", txt):
        p(txt[max(0, m.start()-200): m.start()+400]); break
    i = txt.find("FII DII Activity"); p(txt[i:i+1200])

def moneycontrol():
    for u in ["https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php",
              "https://www.nseindia.com/api/fiidiiTradeReact"]:
        r = requests.get(u, headers=UA, timeout=20); p(u, r.status_code, len(r.text))

t("nse_api", nse_api)
t("block", nse_csv("https://nsearchives.nseindia.com/content/equities/block.csv"))
t("bulk", nse_csv("https://nsearchives.nseindia.com/content/equities/bulk.csv"))
t("5paisa", fivepaisa)
t("mc", moneycontrol)
publish()
