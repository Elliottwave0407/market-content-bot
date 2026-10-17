"""Runs the results poller repeatedly inside one GitHub Actions job (public repo = free minutes).
POLL_LOOP_MINUTES: how long to keep looping. POLL_INTERVAL: seconds between polls."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import ci_out
import results_poller as rp
try:
    import market_posts as mp
    mp.SEND = os.environ.get('POLL_SEND', '0') == '1'
except Exception as _e:
    mp = None
    print('market_posts unavailable:', repr(_e)[:120])

LOOP_MIN = float(os.environ.get("POLL_LOOP_MINUTES", "345"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
try:
    import news_posts as npst
    npst.SEND = os.environ.get('POLL_SEND', '0') == '1'
except Exception as _e:
    npst = None
    print('news_posts unavailable:', repr(_e)[:120])
try:
    import nse_results as nse
    nse.SEND = os.environ.get('POLL_SEND', '0') == '1'
except Exception as _e:
    nse = None
    print('nse_results unavailable:', repr(_e)[:120])
try:
    import xbuttons as xb
except Exception as _e:
    xb = None
    print('xbuttons unavailable:', repr(_e)[:120])
from bse import BSE

def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True)

def commit_state():
    git("add", "state", "feedback")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", "Poller state")
        for _ in range(3):
            if git("pull", "--rebase", "-q", "origin", "main").returncode == 0 and git("push", "-q", "origin", "main").returncode == 0:
                return
            time.sleep(2)

def main():
    git("config", "user.name", "market-content-bot")
    git("config", "user.email", "bot@users.noreply.github.com")
    end = time.time() + LOOP_MIN * 60
    keep, n, sent = [], 0, 0
    news_dirty, last_news_commit = False, 0.0
    known = set()
    while time.time() < end:
        try:
            with BSE(download_folder="./") as bse:      # fresh session every 60 polls
                for _ in range(60):
                    if time.time() >= end:
                        break
                    n += 1
                    fast = bool(known) and n % 30 != 0   # full re-sync of today every 30 polls
                    ci_out.OUT.clear()
                    t0 = time.time()
                    try:
                        posted = rp.main(bse, known, fast) or 0
                    except Exception as e:
                        ci_out.p("Caught error:", rp.redact(repr(e))[:300])
                        posted = -1
                    interesting = any(not x.startswith(("mode=", "done:")) for x in ci_out.OUT)
                    if posted != 0 or interesting:
                        sent += max(posted, 0)
                        keep += [f"[poll {n} {time.strftime('%H:%M:%S')}] "] + ci_out.OUT
                        if posted > 0:
                            commit_state()
                    if mp is not None:
                        try:
                            mchanged, mlines = mp.tick()
                            if mlines:
                                keep += [f"[market {time.strftime('%H:%M:%S')}] "] + mlines
                            if mchanged:
                                commit_state()
                        except Exception as e:
                            keep.append("market tick error: " + rp.redact(repr(e))[:200])
                    if xb is not None and os.environ.get('POLL_SEND', '0') == '1':
                        try:
                            xlines = xb.poll()
                            if any(z.startswith('feedback: saved') for z in xlines):
                                commit_state()
                            rest = [z for z in xlines if not z.startswith('feedback: saved')]
                            if rest:
                                keep += [f"[x {time.strftime('%H:%M:%S')}] "] + rest
                        except Exception as e:
                            keep.append("x-button error: " + rp.redact(repr(e))[:200])
                    if npst is not None:
                        try:
                            nchanged, nlines = npst.tick(bse)
                            if nlines:
                                keep += [f"[news {time.strftime('%H:%M:%S')}] "] + nlines
                            if nchanged:
                                news_dirty = True
                            if news_dirty and time.time() - last_news_commit > 180:   # news state: commit at most every 3 min
                                commit_state()
                                news_dirty, last_news_commit = False, time.time()
                        except Exception as e:
                            keep.append("news tick error: " + rp.redact(repr(e))[:200])
                    if nse is not None:
                        try:
                            schanged, slines = nse.tick()
                            if slines:
                                keep += [f"[nse {time.strftime('%H:%M:%S')}] "] + slines
                            if schanged:
                                commit_state()
                        except Exception as e:
                            keep.append("nse tick error: " + rp.redact(repr(e))[:200])
                    keep = keep[-150:]
                    time.sleep(max(1, INTERVAL - (time.time() - t0)))
        except Exception as e:
            keep.append("session error: " + rp.redact(repr(e))[:200])
            time.sleep(15)
    commit_state()
    ci_out.OUT[:] = [f"loop finished: {n} polls, {sent} posted"] + keep
    ci_out.publish()

main()
