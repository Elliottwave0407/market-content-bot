#!/usr/bin/env bash
# usage: safe_push.sh "<commit message>" <path> [<path> ...]
# Commits the given store paths and pushes. If the rebase conflicts on the concall store (another engine wrote the same month files), keeps our work, resets to origin and unions the two copies record by record, then pushes.
MSG="$1"; shift
git config user.name market-content-bot && git config user.email bot@users.noreply.github.com
for p in "$@"; do git add "$p" 2>/dev/null || true; done
git diff --cached --quiet && { echo "nothing to save"; exit 0; }
git commit -q -m "$MSG"
for i in 1 2 3; do
  if git pull --rebase -q origin main && git push -q origin main; then echo "pushed"; exit 0; fi
  git rebase --abort 2>/dev/null
  echo "conflict or push failure (attempt $i): union and retry"
  rm -rf /tmp/mine && mkdir -p /tmp/mine && for p in "$@"; do [ -d "$p" ] && mkdir -p /tmp/mine/$(basename $p) && cp -r $p/. /tmp/mine/$(basename $p)/; done
  git fetch -q origin main && git reset -q --hard origin/main
  for p in "$@"; do
    b=$(basename $p)
    if [ "$b" = "concall_facts" ] && [ -d /tmp/mine/$b ]; then python3 scripts/store_union.py /tmp/mine/$b $p
    elif [ -d /tmp/mine/$b ]; then cp -r /tmp/mine/$b/. $p/; fi
    git add "$p" 2>/dev/null || true
  done
  git diff --cached --quiet && { echo "nothing left to save after union"; exit 0; }
  git commit -q -m "$MSG (merged)"
done
echo "could not push after 3 attempts"; exit 1
