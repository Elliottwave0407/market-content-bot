import requests, re
from ci_out import p, publish
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get("https://www.5paisa.com/share-market-today/fii-dii-data", headers=UA, timeout=20)
from bs4 import BeautifulSoup
s = BeautifulSoup(r.text, "html.parser")
tabs = s.find_all("table")
p("tables", len(tabs))
for i, t in enumerate(tabs[:3]):
    rows = t.find_all("tr")
    p("TABLE", i, "rows", len(rows))
    for tr in rows[:16]:
        p(" | ".join(c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])))
publish()
