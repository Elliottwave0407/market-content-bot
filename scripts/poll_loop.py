"""Runs the results poller repeatedly inside one GitHub Actions job (public repo = free minutes).
POLL_LOOP_MINUTES: how long to keep looping. POLL_INTERVAL: seconds between polls."""
import os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import ci_out
import results_poller as rp

LOOP_MIN = float(os.environ.get("POLL_LOOP_MINUTES", "345"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "40"))

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
    while time.time() < end:
        n += 1
        ci_out.OUT.clear()
        try:
            posted = rp.main() or 0
        except Exception as e:
            ci_out.p("Caught error:", rp.redact(repr(e))[:300])
            posted = -1
        if posted != 0:
            sent += max(posted, 0)
            keep += [f"[iter {n} {time.strftime('%H:%M:%S')}] "] + ci_out.OUT
            if posted > 0:
                commit_state()
        keep = keep[-150:]
        time.sleep(INTERVAL)
    commit_state()
    ci_out.OUT[:] = [f"loop finished: {n} polls, {sent} posted"] + keep
    ci_out.publish()

main()
