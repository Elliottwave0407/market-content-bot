"""Annual report DEEP reader (pilot, 25 Nov 2026). Reads the WHOLE report in chunks, extracts literal facts only (no PDF stored), merges across chunks.
Writes store/<OUT_DIR>/<ISIN>_<FY>.json. Key from env NVIDIA_API_KEY (never printed). env: OUT_DIR, FY, ISINS (comma list) or MAXN, BUDGET_MIN, CHUNK, MAXCHUNKS."""
import os, re, io, json, time, zipfile, subprocess, tempfile, sys, requests
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store") + "/"
OUT = R + os.environ.get("OUT_DIR", "annual_report_deep_dry") + "/"; os.makedirs(OUT, exist_ok=True)
FY = int(os.environ.get("FY", "2026")); BUDGET = float(os.environ.get("BUDGET_MIN", "40")) * 60; MAXN = int(os.environ.get("MAXN", "5"))
CHUNK = int(os.environ.get("CHUNK", "40000")); MAXCH = int(os.environ.get("MAXCHUNKS", "25"))
MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-ultra-550b-a55b"); NV = os.environ.get("NVIDIA_API_KEY", "").strip()
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
PROMPT = """You read ONE part of an Indian listed company's annual report. Extract ONLY what is literally stated in this part. Return ONLY JSON; omit keys with nothing; never guess or infer; no opinions. Amounts in Rs crore (convert lakh/million if stated), keep units otherwise.
{"business":{"description":"what the company does, 1-2 sentences","products":[{"name":"","share_of_revenue_pct":null,"note":""}],"customers":[""],"geographies":[{"name":"","share_pct":null}],"plants":[{"location":"","capacity":""}],"raw_materials":[""],"competitors_named":[""],"value_chain_position":"manufacturer|contractor|trader|service|other","end_markets":[""],"brands_or_certifications":[""]},
"outlook":[{"statement":"","period":""}],"capex_plans":[{"item":"","amount_cr":null,"timeline":""}],"orders_or_contracts":[{"statement":"","value_cr":null}],"risks":[""],
"subsidiaries":[{"name":"","holding_pct":null,"business":""}],"related_party":[{"party":"","nature":"","amount_cr":null}],"contingent_liabilities":[{"nature":"","amount_cr":null}],"borrowings":[{"lender_or_type":"","amount_cr":null,"note":""}],
"auditor":{"name":"","opinion":"","key_audit_matters":[""],"qualifications_or_emphasis":[""]},"governance":{"promoter_holding_pct":null,"promoter_pledge_pct":null,"top_shareholders":[{"name":"","pct":null}],"director_changes":[""],"auditor_change":""},
"litigation":[""],"people":{"employees":null,"key_management":[{"name":"","role":""}]},"dividend_per_share":null,"other_notable":[""]}"""
def fetch(url):
    urls = [url] + ([url.replace("AttachLive", "AttachHis")] if "AttachLive" in url else []); r = None
    for u in urls:
        try: r = requests.get(u, headers=H, timeout=180)
        except Exception: r = None; continue
        if r.status_code == 200 and len(r.content) >= 5000: break
    if r is None or r.status_code != 200 or len(r.content) < 5000: return None
    b = r.content
    if b[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(b)); n = [x for x in z.namelist() if x.lower().endswith(".pdf")]
        if not n: return None
        b = z.read(max(n, key=lambda x: z.getinfo(x).file_size))
    return b
def text_of(pdf):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf); f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=300).stdout
def chunks(t):
    t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t); out = []; i = 0
    while i < len(t) and len(out) < MAXCH:
        j = min(len(t), i + CHUNK)
        if j < len(t):
            k = t.rfind("\n", i + CHUNK - 3000, j); j = k if k > i else j
        out.append(t[i:j]); i = j
    return out, len(t)
def ask(text):
    for a in range(5):
        try:
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + NV}, timeout=300,
                json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT + "\n\nPART:\n" + text}], "max_tokens": 3500, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}})
            if r.status_code in (429, 502, 503, 504): time.sleep(15 * (a + 1)); continue
            if r.status_code != 200: return None
            s = re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"].get("content") or "", flags=re.S)
            m = re.search(r"\{.*\}", s, re.S); return json.loads(m.group(0)) if m else None
        except Exception: time.sleep(8)
    return None
def merge(acc, new):
    for k, v in (new or {}).items():
        if v in (None, "", [], {}): continue
        if isinstance(v, list):
            L = acc.setdefault(k, [])
            for x in v:
                if x not in L and x not in ("", None): L.append(x)
        elif isinstance(v, dict):
            merge(acc.setdefault(k, {}), v)
        else:
            if k not in acc or acc[k] in (None, ""): acc[k] = v
    return acc
if not NV: print("NVIDIA_API_KEY missing"); sys.exit(0)
recs = {}
for l in open(R + "annual_reports/merged.jsonl"):
    r = json.loads(l)
    if r["fy"] == FY and r.get("isin") and r.get("url"): recs[r["isin"]] = r
want = [x for x in os.environ.get("ISINS", "").split(",") if x] or list(recs)
t0 = time.time(); n = 0
for isin in want:
    if n >= MAXN or time.time() - t0 > BUDGET: break
    r = recs.get(isin); fn = OUT + "%s_%d.json" % (isin, FY)
    if not r or os.path.exists(fn): continue
    n += 1
    try:
        pdf = fetch(r["url"]); t = text_of(pdf) if pdf else ""
        if len(t) < 8000: json.dump({"isin": isin, "fy": FY, "src": r["url"], "skip": "no_text_or_unfetchable", "chars": len(t)}, open(fn, "w")); print(isin, "skip", len(t)); continue
        cs, total = chunks(t); acc = {}; ok = 0
        for c in cs:
            f = ask(c)
            if f: merge(acc, f); ok += 1
        json.dump({"isin": isin, "name": r["name"], "fy": FY, "src": r["url"], "model": MODEL, "chars": total, "chunks": len(cs), "chunks_ok": ok, "facts": acc}, open(fn, "w"), indent=1)
        print(isin, r["name"][:26], "chars", total, "chunks %d/%d" % (ok, len(cs)), "%ds" % (time.time() - t0))
    except Exception as e: print(isin, "error", str(e)[:80])
print("done", n)
