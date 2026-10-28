"""Read-only: does BSE's quote data (equityMetaInfo / resultsSnapshot) carry PE / EPS for BSE SME stocks in ESM? Prints field names and PE-like values only."""
import os, sys, json, re, tempfile, traceback, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
try:
    from bse import BSE
    lst = json.load(open("store/esm/bse_latest.json"))["list"]
    mc = json.load(open("store/mcap/mcap.json"))
    sme = [(v["code"], v["name"], v["st"], i) for i, v in lst.items() if (mc.get(i) or {}).get("g") in ("M", "MT", "MS")]
    p("BSE SME in ESM:", len(sme))
    got = pe_ok = 0; first = True; rows = []
    with BSE(download_folder=tempfile.mkdtemp()) as b:
        for code, name, st, isin in sme:
            try:
                m = b.equityMetaInfo(code)
            except Exception as e:
                rows.append((code, name[:22], "ERR " + type(e).__name__)); continue
            got += 1
            flat = {}
            def walk(o, pre=""):
                if isinstance(o, dict):
                    for k, v in o.items(): walk(v, pre + k + ".")
                elif isinstance(o, list):
                    for n, v in enumerate(o[:3]): walk(v, pre + f"{n}.")
                else: flat[pre[:-1]] = o
            walk(m)
            if first: p("fields:", sorted(flat)[:80]); first = False
            pe = {k: v for k, v in flat.items() if re.search(r"(^|\.)(pe|eps|p/?e.*|.*ttm.*|.*roe.*)$", k, re.I)}
            if any(v not in (None, "", "-", 0, "0") for v in pe.values()): pe_ok += 1
            rows.append((code, name[:22], st, pe))
            time.sleep(0.3)
    p(f"quote ok {got}/{len(sme)} | with PE/EPS-like value {pe_ok}")
    for r in rows[:30]: p("  ", r)
except Exception: p("ERROR", traceback.format_exc()[-600:])
publish()
