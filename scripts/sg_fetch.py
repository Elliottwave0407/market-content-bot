"""Read-only probe: print balance sheet, cash flow and capex text from a company's result PDF and annual report.
Posts nothing, writes no state. Env: RES (BSE attachment name of the result PDF), AR (BSE attachment name of the annual report), AR_NSE (optional NSE archive URL)."""
import os, re, sys
import requests
import fitz

UA = {"User-Agent": "Mozilla/5.0"}
RES = (os.environ.get("RES") or "").strip()
AR = (os.environ.get("AR") or "").strip()
AR_NSE = (os.environ.get("AR_NSE") or "").strip()
KEYS = re.compile(
    r"balance sheet|cash flow|purchase of property|purchase of fixed|capital work|capital advances|property, plant|"
    r"capital commitment|borrowings|trade receivables|trade payables|inventories|cash and cash equivalents|net debt|"
    r"capacity|manufacturing facilit|capex|capital expenditure", re.I)


def get(urls):
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=90)
        except Exception as e:
            print("GET fail", u[:90], repr(e)[:80])
            continue
        print("GET", r.status_code, len(r.content), u[:100])
        if r.content[:4] == b"%PDF":
            return r.content
    return b""


def dump(label, content, only_pages=None, cap=26000, must=None):
    d = fitz.open(stream=content, filetype="pdf")
    print(f"===== {label}: {d.page_count} pages")
    out = 0
    for i in range(d.page_count):
        t = d[i].get_text()
        if must and not re.search(must, t, re.I):
            continue
        if not KEYS.search(t):
            continue
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n", t)
        print(f"----- {label} page {i + 1}")
        print(t[:3800])
        out += len(t[:3800])
        if out > cap:
            print("(cap reached)")
            break


if RES:
    c = get([f"https://www.bseindia.com/xml-data/corpfiling/{f}/{RES}" for f in ("AttachLive", "AttachHis")])
    if c:
        dump("RESULT", c, cap=30000)
    else:
        print("result PDF not downloadable")
if AR or AR_NSE:
    urls = [f"https://www.bseindia.com/xml-data/corpfiling/{f}/{AR}" for f in ("AttachLive", "AttachHis")] if AR else []
    if AR_NSE:
        urls.append(AR_NSE)
    c = get(urls)
    if c:
        dump("ANNUAL_REPORT", c, cap=36000, must=r"purchase of property|capital work|capital commitment|cash flow|capacity")
    else:
        print("annual report not downloadable")
