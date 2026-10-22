"""Read-only: NSE results-comparision (structured re_* fields): does it carry the newest quarter, and when was it created?"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nr
REF = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"
SHOW = ("re_from_dt","re_to_dt","re_create_dt","re_net_sale","re_oth_inc","re_tot_inc","re_tot_exp","re_pro_loss_bef_tax","re_curr_tax","re_deff_tax","re_net_profit","re_con_pro_loss","re_basic_eps","re_depr_und_exp","re_int_new","re_excepn_items_new","re_audited","re_con_nonco","re_desc","re_seq_num","re_res_type","re_period")
try:
    for sym in ("HAVELLS", "NAM-INDIA", "TINNARUBR", "CHENNPETRO"):
        r = nr.sess().get(f"https://www.nseindia.com/api/results-comparision?symbol={sym}", headers={"Referer": REF}, timeout=40)
        j = r.json()
        rows = j if isinstance(j, list) else (j.get("resCmpData") or j.get("data") or [])
        p(sym, r.status_code, "rows", len(rows), "top-level keys", list(j.keys())[:10] if isinstance(j, dict) else "list")
        for x in rows[:4]:
            p("  ", json.dumps({k: x.get(k) for k in SHOW if k in x}))
        if sym == "HAVELLS" and rows:
            p("  all keys", sorted(rows[0].keys()))
except Exception as e:
    import traceback; p("ERROR", repr(e), traceback.format_exc()[-600:])
publish()
