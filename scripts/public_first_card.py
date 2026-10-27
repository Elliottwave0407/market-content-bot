"""Send the latest FII/DII card to the FinGod PUBLIC group only (never to the market group), reusing the exact card builder of market_posts.do_fii.
Sends only when CONFIRM=yes. Does not commit any state."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_out import p, publish
import market_posts as mp
import channel_copy
sent = []
def _only_public(items):
    for it in items:
        r = channel_copy.copy_photo(it[0], it[1])
        sent.append((os.path.basename(it[0]), bool(r and r.get("ok"))))
    return bool(sent) and all(ok for _, ok in sent)
confirm = os.environ.get("CONFIRM", "").strip().lower() == "yes"
mp.FORCE = True; mp.COMMIT = False; mp.QUIET = False; mp.SEND = True
if confirm:
    mp.post = _only_public
else:
    mp.post = lambda items: (p("DRY RUN - card built, not sent:", [os.path.basename(i[0]) for i in items], "| caption:", items[0][1][:300].replace("\n", " / ")) or False)
try:
    mp.do_fii()
except Exception as e:
    p("ERROR", type(e).__name__, str(e)[:200])
p("result:", sent if confirm else "dry run")
publish()
