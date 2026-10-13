import sys, os, json, glob
sys.path.insert(0, os.path.dirname(__file__))
from ci_out import p, publish
import prices
prices.ensure(days_back=int(os.environ.get("DAYS_BACK", "430")), log=p)
files = sorted(glob.glob(os.path.join(prices.DIR, "*.csv.gz")))
p("day files:", len(files), "| first:", os.path.basename(files[0])[:10], "| last:", os.path.basename(files[-1])[:10], "| holiday markers:", len(glob.glob(os.path.join(prices.DIR, "*.skip"))))
df = prices.load()
p("rows:", len(df), "| symbols:", df["sym"].nunique())
per = df.groupby("date")["sym"].count()
p("rows/day min/median/max:", int(per.min()), int(per.median()), int(per.max()))
b = prices.breadth(df)
p(json.dumps(b))
# sanity on split adjustment: biggest raw one-day moves vs adjusted
adj = prices.adjusted(df)
a = adj[adj["date"] == b["date"]].copy()
a["chg"] = (a["close"] / a["prev"] - 1) * 100
p("top 5 gainers:", [(r.sym, round(r.chg, 1)) for r in a[a.series == "EQ"].nlargest(5, "chg").itertuples()])
p("top 5 losers:", [(r.sym, round(r.chg, 1)) for r in a[a.series == "EQ"].nsmallest(5, "chg").itertuples()])
publish()
