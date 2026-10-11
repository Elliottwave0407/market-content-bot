"""Runs the results poller repeatedly inside one GitHub Actions job (public repo = free minutes).
POLL_LOOP_MINUTES: how long to keep looping. POLL_INTERVAL: seconds between polls."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import ci_out
import results_poller as rp

LOOP_MIN = float(os.environ.get("POLL_LOOP_MINUTES", "345"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
from bse import BSE

def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True)

def commit_state():
    git("add", "state")
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
                    if posted != 0:
                        sent += max(posted, 0)
                        keep += [f"[poll {n} {time.strftime('%H:%M:%S')}] "] + ci_out.OUT
                        if posted > 0:
                            commit_state()
                    keep = keep[-150:]
                    time.sleep(max(1, INTERVAL - (time.time() - t0)))
        except Exception as e:
            keep.append("session error: " + rp.redact(repr(e))[:200])
            time.sleep(15)
    commit_state()
    ci_out.OUT[:] = [f"loop finished: {n} polls, {sent} posted"] + keep
    ci_out.publish()

main()
