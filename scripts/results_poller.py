import os, sys, json, re, time
from datetime import datetime, timedelta
import requests
from bse import BSE
from ci_out import p, publish
import results_fetcher as rf
import card

SEND = os.environ.get("POLL_SEND", "0") == "1"
MAX_POSTS = int(os.environ.get("POLL_MAX", "30"))
DAYS_BACK = int(os.environ.get("POLL_DAYS", "1"))
MIN_CR = float(os.environ.get("POLL_MIN_CR", "0"))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
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

def fetch_filings(bse):
    rows = []
    for back in range(DAYS_BACK, -1, -1):
        d = datetime.now() - timedelta(days=back)
        pg, total_seen = 1, 0
        while pg <= 40:
            data = bse.announcements(page_no=pg, from_date=d, to_date=d)
            t = data.get("Table", [])
            if not t:
                break
            total_seen += len(t)
            rows += [r for r in t if r.get("CATEGORYNAME") == "Result"]
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

def build(bse, rec):
    """Return (kind, text, png_path or None, key) or None to skip silently."""
    code, name = str(rec["SCRIP_CD"]), rec["SLONGNAME"]
    headline = (rec.get("NEWSSUB") or "") + " " + (rec.get("HEADLINE") or "")
    filed = datetime.fromisoformat((rec.get("NEWS_DT") or "")[:19])
    lk = link(rec)
    res = rf.results_for_filing(bse, code, name, headline, filed)
    st = res["status"]
    if st == "quarter_unverified":
        return stub(name, code, None, "quarter not identified from the filing headline", lk, f"{code}|unverified|{rec['NEWSID']}")
    if st == "not_available":
        return stub(name, code, res["quarter"], "structured data not available from BSE for this format", lk, f"{code}|{res['quarter']}|na")
    if st == "ok_limited":
        s = res["snapshot"]
        return stub(name, code, res["quarter"], "only limited data available from BSE for this format", lk, f"{code}|{res['quarter']}|limited")
    basis = "consolidated" if res["consolidated"] else "standalone"
    q = rf.expected_quarter(headline, filed)
    quarters = [{"q": rf.qlabel(q - i), "m": rf.fetch(bse, code, name, basis, q - i)} for i in range(5)]
    if not quarters[0]["m"] or not quarters[1]["m"]:
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
           f"Filing: {lk}\n\n{DISC}")
    return ("photo", cap, png, f"{code}|{res['quarter']}|{basis}")

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    st = load_state()
    chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    posted = 0
    with BSE(download_folder="./") as bse:
        filings = fetch_filings(bse)
        new = [r for r in filings if r["NEWSID"] not in st["ids"]]
        p(f"mode={'SEND' if SEND else 'DRY-RUN'} filings={len(filings)} new={len(new)} cap={MAX_POSTS}")
        lines = []
        for rec in new:
            try:
                out = build(bse, rec)
            except Exception as e:
                p(f"ERROR {rec.get('SLONGNAME')}: {redact(repr(e))[:200]}")
                continue
            kind, text, png, key = out
            if kind != "line" and posted >= MAX_POSTS:
                continue
            if key in st["posted"]:
                p(f"dup skip {key}")
                st["ids"].append(rec["NEWSID"])
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
