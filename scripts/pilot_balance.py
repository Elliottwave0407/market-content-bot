import os, sys, traceback, json
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import nse_results as nse, fin_data as fd, store
SYM = os.environ.get("SYMBOL", "E2E").strip().upper()
try:
    s = nse.sess(); b = fd.balance_sheets(s, SYM)
    store.save(SYM, "balance.json", {"unit": "Rs Cr", "source": "NSE integrated-filing XBRL (half-yearly: Mar and Sep)", "periods": b})
    p("periods:", sorted(b))
    for k, v in sorted(b.items()): p(k, v["basis"], "debt", (v["borrowings_noncurrent"] or 0) + (v["borrowings_current"] or 0), "cash", (v["cash"] or 0) + (v["other_bank_balances"] or 0), "equity", v["equity"], "cfo_ytd", v["cfo_ytd"], "capex_ytd", v["capex_ytd"])
except Exception:
    p("ERR", traceback.format_exc()[-700:])
publish()
