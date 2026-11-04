"""Result-event table: one row per company and quarter with the earliest result-filing timestamp we have (NSE side), from 1 Apr 2024.
Plain code, no AI. Sources: store/results_hist/filings.jsonl (NSE, Apr 2024 - Aug 2026) and store/results_if/filings.jsonl (NSE integrated filings, Apr 2025 onward).
Key: (isin, quarter_end). When a company filed standalone and consolidated, or an original and a revised version, the earliest timestamp is the event time.
BSE-only companies are added by a separate step (BSE announcements history). Writes store/result_events/events.jsonl and prints coverage."""
import os, sys, json, collections
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish

START = datetime(2024, 4, 1)
OUT = "store/result_events"


def load(path):
    out = []
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding="utf-8"):
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def pdt(s):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def qend(r):
    d = pdt((r.get("to") or "").title())
    return d.strftime("%Y-%m-%d") if d else None


def qc_end(qc):
    """BSE quarter code -> quarter-end date string."""
    n = int(round(qc)) - 129
    months = n * 3 + 3
    y = 2026 + (months - 1) // 12
    m = (months - 1) % 12 + 1
    import calendar
    return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def main():
    ev = {}
    for src, path in (("hist", "store/results_hist/filings.jsonl"), ("if", "store/results_if/filings.jsonl")):
        for r in load(path):
            f = pdt(r.get("filed") or "")
            qe = qend(r)
            if not f or not qe or f < START:
                continue
            key = (r.get("isin") or r.get("sym"), qe)
            row = {"isin": r.get("isin"), "sym": r.get("sym"), "name": r.get("name"), "idx": r.get("idx"), "qend": qe,
                   "filed": f.strftime("%Y-%m-%d %H:%M:%S"), "basis": [], "src": src}
            cur = ev.get(key)
            if cur is None or row["filed"] < cur["filed"]:
                row["basis"] = (cur or {}).get("basis", [])
                ev[key] = row
                cur = row
            b = (r.get("cons") or "")[:4].lower()
            if b and b not in cur["basis"]:
                cur["basis"].append(b)
    # BSE side: earliest BSE filing per (isin or scrip, quarter end); merged with NSE by ISIN + quarter end, earliest timestamp wins
    isin_by_scrip = {}
    try:
        for isin, v in json.load(open("store/mcap/mcap.json")).items():
            if v.get("s") is not None:
                isin_by_scrip[str(v["s"]).strip()] = isin
    except Exception as e:
        p("mcap map missing:", e)
    n_b = n_unq = 0
    pending = []
    for r in load("store/result_events/bse_raw.jsonl"):
        try:
            f = datetime.strptime(r.get("filed") or "", "%Y-%m-%d %H:%M:%S")
        except Exception:
            f = None
        if not f or f < START:
            continue
        inferred = False
        if not r.get("qcode"):
            n_unq += 1
            # headline names no quarter: latest quarter end at least 7 days before filing (flagged 'inferred'; only used if no placed event exists for it)
            import calendar
            y, m = f.year, f.month
            cands = []
            for k in range(0, 8):
                mm = m - k
                yy = y
                while mm <= 0:
                    mm += 12; yy -= 1
                if mm in (3, 6, 9, 12):
                    cands.append(datetime(yy, mm, calendar.monthrange(yy, mm)[1]))
            qd = next((c for c in cands if (f - c).days >= 7), None)
            if qd is None:
                continue
            r = dict(r, qcode=129 + ((qd.year - 2026) * 12 + (qd.month - 3)) // 3)
            inferred = True
        if "board meeting" in (r.get("head") or "").lower() and "result" not in (r.get("head") or "").lower():
            continue
        qe = qc_end(r["qcode"])
        isin = isin_by_scrip.get(r["code"])
        key = (isin or "BSE:" + r["code"], qe)
        fs = f.strftime("%Y-%m-%d %H:%M:%S")
        cur = ev.get(key)
        if inferred:
            pending.append((key, isin, r, fs, qe))
            continue
        n_b += 1
        if cur is None:
            ev[key] = {"isin": isin, "sym": None, "scrip": r["code"], "name": r.get("name"), "idx": "bse", "qend": qe, "filed": fs, "basis": [], "src": "bse", "first": "bse", "bse_filed": fs}
        else:
            cur["scrip"] = r["code"]
            cur["bse_filed"] = min(cur.get("bse_filed") or fs, fs)
            if fs < cur["filed"]:
                cur["filed"] = fs; cur["first"] = "bse"
            else:
                cur.setdefault("first", cur.get("src"))
    n_inf = 0
    for key, isin, r, fs, qe in pending:
        if key in ev:
            continue      # a placed filing already covers this company and quarter: the unplaced one is an extra (revision, other notice)
        ev[key] = {"isin": isin, "sym": None, "scrip": r["code"], "name": r.get("name"), "idx": "bse", "qend": qe, "filed": fs, "basis": [], "src": "bse", "first": "bse", "bse_filed": fs, "inferred": True}
        n_inf += 1
    p("events added from BSE rows with an inferred quarter:", n_inf)
    for r in ev.values():
        r.setdefault("first", r.get("src"))
        # BSE time is the announcement time. NSE time in these feeds is the structured-data (XBRL) submission time, which usually comes after the announcement.
        r["ts_kind"] = "bse_announcement" if r["first"] == "bse" else "nse_xbrl"
    p("BSE rows used:", n_b, "BSE rows without a quarter in the headline (not placed):", n_unq)
    rows = sorted(ev.values(), key=lambda r: (r["qend"], r["filed"]))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "events.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    p("result events:", len(rows), "companies:", len({r['isin'] or r['sym'] for r in rows}))
    byq = collections.Counter(r["qend"] for r in rows)
    for q, n in sorted(byq.items()):
        p(" ", q, n)
    p("first seen on:", dict(collections.Counter(r.get("first") for r in rows)))
    both = [r for r in rows if r.get("bse_filed") and r.get("src") in ("hist", "if")]
    p("dual-listed: first on NSE", sum(1 for r in both if r["first"] != "bse"), "first on BSE", sum(1 for r in both if r["first"] == "bse"))
    p("both exchanges:", sum(1 for r in rows if r.get("bse_filed") and r.get("src") in ("hist", "if")))
    p("SME-board rows:", sum(1 for r in rows if r["idx"] == "sme"))
    publish()


main()
