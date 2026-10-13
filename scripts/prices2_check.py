import sys, os, json, glob
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import prices2
prices2.ensure(days_back=int(os.environ.get("DAYS_BACK", "430")), log=p)
nse = sorted(glob.glob(os.path.join(prices2.DIR, "*.nse.csv.gz"))); bse = sorted(glob.glob(os.path.join(prices2.DIR, "*.bse.csv.gz")))
p("NSE day files:", len(nse), "| BSE day files:", len(bse), "| skips:", len(glob.glob(os.path.join(prices2.DIR, "*.skip"))), "| bse.none:", len(glob.glob(os.path.join(prices2.DIR, "*.bse.none"))))
df = prices2.load()
p("rows:", len(df), "| ISINs:", df["isin"].nunique(), "| primary exchange split:", df.drop_duplicates("isin")["exch"].value_counts().to_dict())
mc = prices2.mcaps()
p("mcap known for ISINs:", len(mc))
b = prices2.breadth_segments(df, mc)
p(json.dumps(b))
publish()
