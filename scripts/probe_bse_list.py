import sys, os, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
from bse import BSE
names = ("ANGEL", "CCL PRODUCTS", "ELECON", "KABRA", "TECH MAHINDRA", "E2E", "SBC EXPORT", "KARUR VYSYA", "ORIENTAL HOTELS", "BOMBAY SUPER")
with BSE(download_folder=tempfile.mkdtemp()) as b:
    allrows = []
    for g in ("A", "B", "T", "X", "XT", "Z", "M", "MT", "MS", "P", "R", "ZP", "IP", "TS", "Y"):
        allrows += b.listSecurities(group=g)
    p("rows:", len(allrows), "with isin:", sum(1 for x in allrows if (x.get("ISIN_NUMBER") or "").strip()))
    for n in names:
        hit = [(x.get("Issuer_Name"), x.get("scrip_id"), x.get("SCRIP_CD"), x.get("ISIN_NUMBER"), x.get("GROUP"), x.get("Status")) for x in allrows if n in (x.get("Issuer_Name") or "").upper() or n in (x.get("Scrip_Name") or "").upper()]
        p(n, "->", hit[:3])
publish()
