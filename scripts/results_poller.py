import os, sys, json, re, time
from datetime import datetime, timedelta
import requests
from contextlib import nullcontext
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
import card

SEND = os.environ.get("POLL_SEND", "0") == "1"
MAX_POSTS = int(os.environ.get("POLL_MAX", "30"))
DAYS_BACK = int(os.environ.get("POLL_DAYS", "1"))
MIN_CR = float(os.environ.get("POLL_MIN_CR", "0"))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WAIT_H = float(os.environ.get("POLL_WAIT_HOURS", "24"))   # how long to wait for BSE numbers before posting a no-numbers card
RETRY_SEC = int(os.environ.get("POLL_RETRY_SEC", "90"))
STATE = "state/seen.json"
OUTDIR = "drafts/poll"
DISC = "Source: BSE filings. Auto-generated from filed numbers - verify with official filings. Not investment advice."

def redact(s):
    return str(s).replace(TOKEN, "<token>") if TOKEN else str(s)

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"ids": [], "posted": []}

def save_state(st):
    os.makedirs("state", exist_ok=True)
    st["ids"] = st["ids"][-5000:]
    st["posted"] = st["posted"][-5000:]
    json.dump(st, open(STATE, "w"), indent=0)

def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", timeout=60, **kw)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"non-json {r.status_code}"}

def fy_label(qlabel):
    d = datetime.strptime(qlabel, "%b-%y")
    qn = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    fy = d.year + 1 if d.month > 3 else d.year
    return f"Q{qn} FY{str(fy)[2:]}" if qn else qlabel

def link(rec):
    a = rec.get("ATTACHMENTNAME")
    return f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{a}" if a else rec.get("NSURL", "")

def fetch_filings(bse, known=None, fast=False):
    """Result filings. known: set of every NEWSID seen so far (updated here).
    fast=True: only the newest page(s) of today, stopping once an already-seen item appears."""
    prior = set(known) if known is not None else set()
    days = [0] if fast else list(range(DAYS_BACK, -1, -1))
    rows = []
    for back in days:
        d = datetime.now() - timedelta(days=back)
        pg, total_seen = 1, 0
        while pg <= 40:
            data = bse.announcements(page_no=pg, from_date=d, to_date=d)
            t = data.get("Table", [])
            if not t:
                break
            total_seen += len(t)
            rows += [r for r in t if r.get("CATEGORYNAME") == "Result"]
            if known is not None:
                known.update(r["NEWSID"] for r in t)
            if fast and any(r["NEWSID"] in prior for r in t):
                break
            if total_seen >= data.get("Table1", [{}])[0].get("ROWCNT", 0):
                break
            pg += 1
    seen, out = set(), []
    for r in rows:
        if r["NEWSID"] not in seen:
            seen.add(r["NEWSID"]); out.append(r)
    out.sort(key=lambda r: r.get("NEWS_DT") or "")
    return out

def stub(name, code, qlabel_, reason, lk, key):
    os.makedirs(OUTDIR, exist_ok=True)
    png = os.path.join(OUTDIR, f"stub_{code}_{qlabel_ or 'unknown'}.png")
    card.render_stub(name, f"BSE {code}", fy_label(qlabel_) if qlabel_ else "Result", reason, png)
    cap = f"{name} {fy_label(qlabel_) if qlabel_ else ''} results filed. Numbers not shown ({reason}).\nFiling: {lk}\n\n{DISC}"
    return ("photo", cap, png, key)

def inferred_qend(filed):
    """Quarter end implied by the filing date, used only when the headline names no quarter."""
    m, y = filed.month, filed.year
    if m in (10, 11, 12): return f"30.09.{y}"
    if m in (1, 2, 3): return f"31.12.{y - 1}"
    if m in (4, 5, 6): return f"31.03.{y}"
    return f"30.06.{y}"

def build(bse, rec, final=False):
    """Return (kind, text, png_path or None, key). kind 'wait' = BSE numbers not there yet, retry later."""
    code, name = str(rec["SCRIP_CD"]), rec["SLONGNAME"]
    headline = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
    filed = datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19])
    lk = link(rec)
    res = rf.results_for_filing(bse, code, name, headline, filed)
    inferred = False
    if res["status"] == "quarter_unverified":
        headline = headline + " quarter ended " + inferred_qend(filed)
        res = rf.results_for_filing(bse, code, name, headline, filed)
        inferred = True
    st = res["status"]
    if st == "quarter_unverified":
        return stub(name, code, None, "quarter not identified from the filing headline", lk, f"{code}|unverified|{rec['NEWSID']}")
    if st in ("not_available", "ok_limited"):
        if not final:
            return ("wait", "numbers not yet on BSE", None, f"{code}|{res['quarter']}|wait")
        reason = "BSE has not published structured numbers for this filing" if st == "not_available" else "only limited data available from BSE for this format"
        return stub(name, code, res["quarter"], reason, lk, f"{code}|{res['quarter']}|na")
    basis = "consolidated" if res["consolidated"] else "standalone"
    q = rf.expected_quarter(headline, filed)
    quarters = [{"q": rf.qlabel(q - i), "m": rf.fetch(bse, code, name, basis, q - i)} for i in range(5)]
    if not quarters[0]["m"]:
        if not final:
            return ("wait", "comparison data incomplete", None, f"{code}|{res['quarter']}|wait")
        return stub(name, code, res["quarter"], "comparison data incomplete", lk, f"{code}|{res['quarter']}|incomplete")
    for qq in quarters:
        if qq["m"] is None:
            qq["m"] = {"revenue": None, "ebitda": None, "pbt": None, "pat": None, "eps": None, "bank": False}
    cur, prev, yago = quarters[0]["m"], quarters[1]["m"], quarters[4]["m"]
    r0, r1 = cur.get("revenue"), prev.get("revenue")
    if r0 and r1 and r0 > 0 and r1 > 0 and (r0 / r1 > 50 or r1 / r0 > 50):
        return stub(name, code, res["quarter"], "figures look inconsistent with the previous quarter - please verify", lk, f"{code}|{res['quarter']}|anomaly")
    sales, pat = card.cr(cur["revenue"]), card.cr(cur["pat"])
    sd = 0 if sales and sales >= 100 else 1
    pd_ = 0 if pat and pat >= 100 else 1
    sy, py = card.fmt_pct(card.pct(cur["revenue"], yago["revenue"])), card.fmt_pct(card.pct(cur["pat"], yago["pat"]))
    if sales is None or sales < MIN_CR:
        return ("line", f"{name} {fy_label(res['quarter'])} {"cons" if basis=="consolidated" else "stand"}: Sales {card.fmt_num(sales, sd)} Cr ({sy} YoY), PAT {card.fmt_num(pat, pd_)} Cr ({py} YoY) | {lk}", None, f"{code}|{res['quarter']}|{basis}")
    png = os.path.join(OUTDIR, f"{code}_{res['quarter']}_{basis}.png")
    card.render(name, f"BSE {code}", basis, quarters, png)
    cap = (f"{name} {fy_label(res['quarter'])} | {basis.capitalize()}\n"
           f"Sales Rs {card.fmt_num(sales, sd)} Cr ({sy} YoY), net profit Rs {card.fmt_num(pat, pd_)} Cr ({py} YoY).\n"
           f"{'(Quarter inferred from filing date.) ' if inferred else ''}Filing: {lk}\n\n{DISC}")
    return ("photo", cap, png, f"{code}|{res['quarter']}|{basis}")

def main(bse_in=None, known=None, fast=False):
    os.makedirs(OUTDIR, exist_ok=True)
    st = load_state()
    chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    posted = 0
    ctx = nullcontext(bse_in) if bse_in is not None else BSE(download_folder="./")
    with ctx as bse:
        filings = fetch_filings(bse, known, fast)
        new = [r for r in filings if r["NEWSID"] not in st["ids"]]
        p(f"mode={'SEND' if SEND else 'DRY-RUN'} filings={len(filings)} new={len(new)} cap={MAX_POSTS}")
        lines = []
        now = time.time()
        pend = st.setdefault("pending", {})
        new_ids = {r["NEWSID"] for r in new}
        retry = [v["rec"] for k, v in list(pend.items()) if k not in new_ids and now - v["last"] >= RETRY_SEC]
        for rec in new + retry:
            nid = rec["NEWSID"]
            first = pend.get(nid, {}).get("first", now)
            try:
                out = build(bse, rec, final=(now - first) > WAIT_H * 3600)
            except Exception as e:
                p(f"ERROR {rec.get('SLONGNAME')}: {redact(repr(e))[:200]}")
                continue
            kind, text, png, key = out
            if kind == "wait":
                if nid not in pend:
                    p(f"[wait] {rec.get('SLONGNAME')} ({key}) - BSE numbers not published yet, will retry")
                pend[nid] = {"rec": rec, "first": first, "last": now}
                continue
            if kind != "line" and posted >= MAX_POSTS:
                continue
            if key in st["posted"]:
                p(f"dup skip {key}")
                st["ids"].append(rec["NEWSID"])
                pend.pop(nid, None)
                continue
            p(f"[{kind}] {key} :: {text[:160]!r}")
            if kind == "line":
                lines.append((rec["NEWSID"], key, text))
                continue
            if SEND:
                r = tg("sendPhoto", data={"chat_id": chat, "caption": text[:1024]}, files={"photo": open(png, "rb")}) if kind == "photo" \
                    else tg("sendMessage", json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
                p(f"  sent ok={r.get('ok')} {redact(r.get('description', ''))}")
                if not r.get("ok"):
                    continue
                time.sleep(3.2)
            st["ids"].append(rec["NEWSID"])
            st["posted"].append(key)
            if nid in pend:
                st.setdefault("lag", []).append([rec.get("SLONGNAME"), round((now - pend[nid]["first"]) / 60)])
                st["lag"] = st["lag"][-300:]
                p(f"  resolved after {round((now - pend[nid]['first']) / 60)} min wait")
                pend.pop(nid, None)
            posted += 1
            if SEND:
                save_state(st)
        # one digest message for smaller companies
        lines = lines[:40]
        if lines:
            body = f"Smaller results (sales below Rs {MIN_CR:.0f} Cr), consolidated if available, else standalone. Filed numbers; verify with filing.\n\n" + "\n".join(l[2] for l in lines)
            p(f"[digest] {len(lines)} lines")
            ok = True
            if SEND:
                r = tg("sendMessage", json={"chat_id": chat, "text": body[:4000], "disable_web_page_preview": True})
                ok = r.get("ok")
                p(f"  digest sent ok={ok} {redact(r.get('description', ''))}")
            if ok:
                for nid, key, _ in lines:
                    st["ids"].append(nid); st["posted"].append(key)
    if SEND:
        save_state(st)
    p(f"done: {posted} {'sent' if SEND else 'would send'}")
    return posted

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        p("Caught error:", redact(repr(e))[:300])
    publish()
    sys.exit(0)
