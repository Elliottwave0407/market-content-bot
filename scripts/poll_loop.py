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
RES_INTERVAL = int(os.environ.get("RESULTS_INTERVAL", "3"))
try:
    import news_posts as npst
    npst.SEND = os.environ.get('POLL_SEND', '0') == '1'
except Exception as _e:
    npst = None
    print('news_posts unavailable:', repr(_e)[:120])
try:
    import sme_results as sme
    sme.SEND = os.environ.get('POLL_SEND', '0') == '1'
except Exception as _e:
    sme = None
    print('sme_results unavailable:', repr(_e)[:120])
try:
    import fin_results as fin
except Exception as _e:
    fin = None
    print('fin_results unavailable:', repr(_e)[:120])
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

import threading
GIT_LOCK = threading.Lock()
KEEP, COUNT = [], {"n": 0, "sent": 0}

def commit_state():
    with GIT_LOCK:
        _commit_state()

def _commit_state():
    git("add", "state", "feedback", "store")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", "Poller state")
        for _ in range(3):
            if git("pull", "--rebase", "-q", "origin", "main").returncode == 0 and git("push", "-q", "origin", "main").returncode == 0:
                return
            time.sleep(2)

XB_LINES, XB_FLAGS = [], {"dirty": False}
LOOPT = []

def xb_thread(end):
    """Button taps are handled in their own thread every ~2 s, so a tap shows up fast even when a main-loop pass is slow."""
    while time.time() < end:
        try:
            xlines = xb.poll()
            if any(z.startswith('feedback: saved') for z in xlines):
                XB_FLAGS["dirty"] = True
            XB_LINES.extend(f"[x {time.strftime('%H:%M:%S')}] " + z for z in xlines if not z.startswith('feedback: saved'))
        except Exception as e:
            XB_LINES.append("x-button error: " + rp.redact(repr(e))[:200])
        time.sleep(2)

def results_thread(end):
    """BSE results get their own loop and their own BSE session, so market/news/NSE/SME/bank ticks can never slow a result card down."""
    known = set()
    n = 0
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
                        COUNT["sent"] += max(posted, 0)
                        KEEP.extend([f"[poll {n} {time.strftime('%H:%M:%S')}] "] + list(ci_out.OUT))
                        if posted > 0:
                            commit_state()
                    LOOPT.append(time.time() - t0)
                    if len(LOOPT) >= 40:
                        KEEP.append(f"[loop] results: last 40 passes avg {sum(LOOPT)/len(LOOPT):.0f}s, max {max(LOOPT):.0f}s per pass")
                        LOOPT.clear()
                    del KEEP[:-150]
                    time.sleep(max(1, RES_INTERVAL - (time.time() - t0)))
        except Exception as e:
            KEEP.append("results session error: " + rp.redact(repr(e))[:200])
            time.sleep(10)
    COUNT["n"] = n

def main():
    git("config", "user.name", "market-content-bot")
    git("config", "user.email", "bot@users.noreply.github.com")
    end = time.time() + LOOP_MIN * 60
    if xb is not None and os.environ.get('POLL_SEND', '0') == '1':
        threading.Thread(target=xb_thread, args=(end,), daemon=True).start()
    keep, n = KEEP, 0
    rt = threading.Thread(target=results_thread, args=(end,), daemon=True)
    rt.start()
    news_dirty, last_news_commit = False, 0.0
    known = set()
    while time.time() < end:
        try:
            with BSE(download_folder="./") as bse:      # fresh session every 60 polls
                for _ in range(60):
                    if time.time() >= end:
                        break
                    n += 1
                    t0 = time.time()
                    if mp is not None:
                        try:
                            mchanged, mlines = mp.tick()
                            if mlines:
                                keep += [f"[market {time.strftime('%H:%M:%S')}] "] + mlines
                            if mchanged:
                                commit_state()
                        except Exception as e:
                            keep.append("market tick error: " + rp.redact(repr(e))[:200])
                    if XB_FLAGS["dirty"]:
                        XB_FLAGS["dirty"] = False
                        commit_state()
                    while XB_LINES:
                        keep.append(XB_LINES.pop(0))
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
                    if sme is not None:
                        try:
                            mchanged2, mlines2 = sme.tick()
                            if mlines2:
                                keep += [f"[sme {time.strftime('%H:%M:%S')}] "] + mlines2
                            if mchanged2:
                                commit_state()
                        except Exception as e:
                            keep.append("sme tick error: " + rp.redact(repr(e))[:200])
                    if fin is not None:
                        try:
                            fch, flines = fin.tick()
                            if flines:
                                keep += [f"[fin {time.strftime('%H:%M:%S')}] "] + flines
                            if fch:
                                commit_state()
                        except Exception as e:
                            keep.append("fin tick error: " + rp.redact(repr(e))[:200])
                    del keep[:-150]
                    time.sleep(max(1, INTERVAL - (time.time() - t0)))
        except Exception as e:
            keep.append("session error: " + rp.redact(repr(e))[:200])
            time.sleep(15)
    rt.join(timeout=60)
    commit_state()
    ci_out.OUT[:] = [f"loop finished: {n} side polls, {COUNT['n']} results polls, {COUNT['sent']} posted"] + keep
    ci_out.publish()

main()
