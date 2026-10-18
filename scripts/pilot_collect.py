"""E2E pilot step 1 (dry run, posts nothing): hard numbers + Trust Check signals from filed data."""
import os, sys, re, json, tempfile, traceback
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import results_fetcher as rf
import nse_results as nse

SYM = os.environ.get("SYMBOL", "E2E").strip()
CODE = os.environ.get("SCRIP", "544783").strip()
NAME = os.environ.get("CNAME", "E2E Networks Limited").strip()
OUT = {}

def numbers(b):
    rows = []
    for q in range(131, 122, -1):                  # Sep-26 back to Sep-24
        m = None
        for basis in ("consolidated", "standalone"):
            try:
                m = rf.fetch(b, CODE, NAME, basis, q)
            except Exception:
                m = None
            if m and m.get("revenue") is not None:
                m = dict(m, basis=basis); break
        if m:
            rows.append((q, m))
    p("== QUARTERLY NUMBERS (Rs Cr, from BSE tables)")
    for q, m in rows:
        rev, eb, pat = m.get("revenue"), m.get("ebitda"), m.get("pat")
        em = round(100 * eb / rev, 1) if rev and eb is not None else None
        pm = round(100 * pat / rev, 1) if rev and pat is not None else None
        p(f"{rf.qlabel(q)} {m['basis'][:4]} | rev {rev} | ebitda {eb} | ebitda% {em} | pat {pat} | pat% {pm} | eps {m.get('eps')}")
    OUT["numbers"] = [(rf.qlabel(q), m) for q, m in rows]

def holding(s):
    p("== PROMOTER / PUBLIC HOLDING (NSE shareholding pattern)")
    try:
        r = s.get("https://www.nseindia.com/api/corporate-share-holdings-master", params={"index": "equities", "symbol": SYM}, headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}, timeout=40)
        j = r.json()
        for x in j[:10]:
            p(f"{x.get('date')} | promoter {x.get('pr_and_prgrp')}% | public {x.get('public_val')}% | revised {x.get('revisedStatus')}")
        OUT["holding"] = [(x.get("date"), x.get("pr_and_prgrp"), x.get("public_val")) for x in j[:10]]
    except Exception as e:
        p("holding err", repr(e)[:80])

def sast_pledge_pit(s):
    H = {"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"}
    p("== SAST (large acquisitions / sales)")
    try:
        j = s.get("https://www.nseindia.com/api/corporate-sast-reg29", params={"index": "equities", "symbol": SYM}, headers=H, timeout=40).json()
        for x in j.get("data", [])[:15]:
            p(f"{x.get('acquirerDate')} | {x.get('acqSaleType')} | {x.get('acquirerName')} | shares {x.get('noOfShareAcq')} | after {x.get('noOfShareAft')} | % after {x.get('totAftAcqSharesPer') or x.get('aftAcqSharesPer')}")
    except Exception as e:
        p("sast err", repr(e)[:80])
    for name, url, params in (("PLEDGE", "https://www.nseindia.com/api/corporate-pledgedata", {"index": "equities", "symbol": SYM}),
                              ("INSIDER (PIT) last 12m", "https://www.nseindia.com/api/corporates-pit", {"index": "equities", "symbol": SYM, "from_date": (datetime.now() - timedelta(days=365)).strftime("%d-%m-%Y"), "to_date": datetime.now().strftime("%d-%m-%Y")})):
        p("==", name)
        try:
            j = s.get(url, params=params, headers=H, timeout=40).json()
            d = j.get("data", [])
            p("records:", len(d))
            for x in d[:12]:
                p(json.dumps({k: x[k] for k in list(x)[:12]})[:300])
        except Exception as e:
            p(name, "err", repr(e)[:80])

KEYS = ("auditor", "resign", "cessation", "change in management", "change in directorate", "credit rating", "sebi", "penalt", "show cause", "monitoring agency", "default", "fraud", "litigation", "disclosure under sebi takeover", "pledge", "preferential", "qip", "allotment", "fund raising", "warrant", "esop", "related party", "outcome of board meeting", "investor presentation", "earnings call transcript", "analyst / investor meet", "financial result", "result")
def announcements(b):
    p("== BSE ANNOUNCEMENTS last 12 months (governance-relevant + results/presentation/transcript)")
    rows = []
    d1 = datetime(2026, 10, 17)
    for i in range(12):
        a, z = d1 - timedelta(days=30 * (i + 1) - 1), d1 - timedelta(days=30 * i)
        pg = 1
        while pg <= 6:
            try:
                d = b.announcements(page_no=pg, from_date=a, to_date=z, scripcode=CODE)
            except Exception as e:
                p("ann err", repr(e)[:60]); break
            t = d.get("Table", [])
            if not t:
                break
            rows += t
            pg += 1
    p("total filings:", len(rows))
    import collections
    c = collections.Counter((x.get("CATEGORYNAME"), x.get("SUBCATNAME")) for x in rows)
    for k, v in c.most_common(30):
        p("  ", v, k)
    p("-- notable")
    for x in sorted(rows, key=lambda x: x.get("NEWS_DT") or ""):
        txt = " ".join(str(x.get(k) or "") for k in ("SUBCATNAME", "NEWSSUB", "HEADLINE")).lower()
        sub = (x.get("SUBCATNAME") or "")
        if any(k in txt for k in KEYS) and sub not in ("Newspaper Publication", "Trading Window", "Loss of Share Certificate"):
            p(f"{(x.get('NEWS_DT') or '')[:10]} | {sub[:34]} | {(x.get('HEADLINE') or x.get('NEWSSUB') or '')[:90]}".replace("\n", " "))
    OUT["n_filings"] = len(rows)
    return rows

def main():
    from bse import BSE
    s = nse.sess()
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        numbers(b)
        announcements(b)
    holding(s)
    sast_pledge_pit(s)

try:
    main()
except Exception:
    p("ERR", traceback.format_exc()[-1200:])
publish()
