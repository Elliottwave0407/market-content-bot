"""Annual report reader (pilot, 23 Nov 2026). Downloads an annual report, extracts the key sections, asks the model for FACTS ONLY
(no PDF stored), writes store/<OUT_DIR>/<ISIN>_<FY>.json. Key from env NVIDIA_API_KEY (never printed). Posts nothing."""
import os, re, io, json, time, zipfile, subprocess, tempfile, sys, requests
R = os.path.join(os.path.dirname(__file__), "..", "store") + "/"
OUT = R + os.environ.get("OUT_DIR", "annual_report_facts_dry") + "/"
FY = int(os.environ.get("FY", "2026")); MAXN = int(os.environ.get("MAXN", "10")); BUDGET = float(os.environ.get("BUDGET_MIN", "40")) * 60
MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-ultra-550b-a55b"); NV = os.environ.get("NVIDIA_API_KEY", "").strip()
os.makedirs(OUT, exist_ok=True); t0 = time.time()
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"}
PROMPT = """You read excerpts of an Indian listed company's annual report. Return ONLY JSON with these keys (null or [] when not stated; never guess):
{"business":"one sentence what the company does","segments":[{"name":"","share_of_revenue_pct":null}],"capacity_or_capex":[{"item":"","amount_cr":null,"timeline":""}],"guidance_or_targets":[{"statement":"","metric":"","value":"","by_when":""}],"order_book_cr":null,"auditor":{"name":"","opinion":"unmodified|qualified|adverse|disclaimer","emphasis_or_qualification":""},"promoter_holding_pct":null,"promoter_pledge_pct":null,"employees":null,"subsidiaries_count":null,"key_risks":[""],"related_party_note":"","contingent_liabilities_cr":null,"dividend_per_share":null}
Every number must be literally in the text. Amounts in Rs crore (convert from lakh/million if stated)."""
SECS = ["management discussion", "business overview", "directors' report", "directors report", "independent auditor", "secretarial audit", "risks and concerns", "outlook", "order book", "capex", "capital expenditure"]
def fetch(url):
    r = requests.get(url, headers=H, timeout=120)
    if r.status_code != 200 or len(r.content) < 5000: return None
    b = r.content
    if b[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(b)); n = [x for x in z.namelist() if x.lower().endswith(".pdf")]
        if not n: return None
        b = z.read(max(n, key=lambda x: z.getinfo(x).file_size))
    return b
def text_of(pdf):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf); f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=180).stdout
def excerpt(t, cap=60000):
    low = t.lower(); out = []; seen = 0
    for s in SECS:
        for m in re.finditer(re.escape(s), low):
            if m.start() < seen: continue
            out.append(t[m.start(): m.start() + 7000]); seen = m.start() + 7000; break
    return "\n----\n".join(out)[:cap]
def ask(text):
    for a in range(5):
        try:
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": "Bearer " + NV}, timeout=300,
                json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT + "\n\nEXCERPTS:\n" + text}], "max_tokens": 3000, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}})
            if r.status_code in (429, 502, 503, 504): time.sleep(15 * (a + 1)); continue
            if r.status_code != 200: return None
            s = re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"].get("content") or "", flags=re.S)
            m = re.search(r"\{.*\}", s, re.S); return json.loads(m.group(0)) if m else None
        except Exception: time.sleep(8)
    return None
if not NV: print("NVIDIA_API_KEY missing"); sys.exit(0)
recs = [json.loads(l) for l in open(R + "annual_reports/merged.jsonl")]
recs = [r for r in recs if r["fy"] == FY and r.get("isin") and r.get("url")]
pages = {x[:-5] for x in os.listdir(os.path.dirname(R) + "/store/company_pages")} if os.path.isdir(R + "company_pages") else set()
recs.sort(key=lambda r: (r["isin"] not in pages, r["isin"]))      # pilot pages first
done = n = fail = 0
for r in recs:
    if n >= MAXN or time.time() - t0 > BUDGET: break
    fn = OUT + "%s_%d.json" % (r["isin"], FY)
    if os.path.exists(fn): continue
    n += 1
    try:
        pdf = fetch(r["url"]); t = text_of(pdf) if pdf else ""
        ex = excerpt(t) if len(t) > 5000 else ""
        if not ex: json.dump({"isin": r["isin"], "fy": FY, "src": r["url"], "skip": "no_text_or_unfetchable", "pdf_chars": len(t)}, open(fn, "w")); fail += 1; print(r["isin"], "skip no text"); continue
        f = ask(ex)
        json.dump({"isin": r["isin"], "name": r["name"], "fy": FY, "src": r["url"], "model": MODEL, "pdf_chars": len(t), "facts": f}, open(fn, "w"), indent=1)
        done += 1 if f else 0; fail += 0 if f else 1; print(r["isin"], r["name"][:28], "ok" if f else "model-fail", "%ds" % (time.time() - t0))
    except Exception as e:
        fail += 1; print(r["isin"], "error", str(e)[:60])
print("done", done, "fail", fail, "of", n)
