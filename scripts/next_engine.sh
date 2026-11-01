#!/usr/bin/env bash
# One NVIDIA-using engine at a time. Called at the end of every engine run (and by the watchdog).
# usage: next_engine.sh <caller>   env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID
# Rule: if any engine is running or queued (other than this run), do nothing (it will call this script when it ends).
# Otherwise start the next engine that still has work, round-robin after the caller: nse-ingest -> reread -> ppt-ingest.
R="$GITHUB_REPOSITORY"; ME="${GITHUB_RUN_ID:-0}"; CALLER="${1:-}"
busy() { gh api "repos/$R/actions/workflows/$1.yml/runs?per_page=20" -q "[.workflow_runs[]|select(.status!=\"completed\" and .id!=$ME)]|length" 2>/dev/null || echo 9; }
for w in concall-extract concall-nse-ingest concall-reread ppt-ingest; do
  b=$(busy $w); echo "$w busy=$b"
  if [ "$b" -gt 0 ]; then echo "another engine is running or queued: not starting one now"; exit 0; fi
done
left() { python3 -c "import json;d=json.load(open('$1'));print(d.get('remaining',0) if d.get('progressed',0)>0 else 0)" 2>/dev/null || echo 0; }
order=(concall-nse-ingest concall-reread ppt-ingest)
start=0; for i in "${!order[@]}"; do [ "${order[$i]}" = "$CALLER" ] && start=$(( (i + 1) % ${#order[@]} )); done
for k in 0 1 2; do
  e="${order[$(( (start + k) % ${#order[@]} ))]}"
  case "$e" in
    concall-nse-ingest) n=$(left store/concall_coverage/_ingest_state.json) ;;
    concall-reread)     n=$(left store/concall_reread/_state_v3.json) ;;
    ppt-ingest)         n=$(left store/ppt_facts/_state.json) ;;
  esac
  echo "$e remaining=$n"
  if [ "$n" -gt 0 ]; then
    sleep 15
    case "$e" in
      concall-nse-ingest) gh api -X POST repos/$R/actions/workflows/concall-nse-ingest.yml/dispatches -f ref=main -f 'inputs[dry]=0' -f 'inputs[maxn]=0' -f 'inputs[budget_min]=150' -f 'inputs[workers]=6' -f 'inputs[statuses]=nse_only,bse_listed_missing,covered_but_skipped' ;;
      concall-reread)     gh api -X POST repos/$R/actions/workflows/concall-reread.yml/dispatches -f ref=main -f 'inputs[dry]=0' -f 'inputs[maxn]=0' -f 'inputs[budget_min]=150' -f 'inputs[workers]=6' -f 'inputs[schema_v]=3' ;;
      ppt-ingest)         gh api -X POST repos/$R/actions/workflows/ppt-ingest.yml/dispatches -f ref=main -f 'inputs[dry]=0' -f 'inputs[maxn]=0' -f 'inputs[budget_min]=150' -f 'inputs[workers]=8' ;;
    esac && echo "started $e"
    exit 0
  fi
done
echo "no engine has work left"
