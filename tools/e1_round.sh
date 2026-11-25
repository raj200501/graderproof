#!/usr/bin/env bash
# One E1/E2 audit round for one benchmark under prereg/0002 as amended by prereg/0003.
# Runs from the detached worktree at the freeze commit (prereg 0003, change 3), writes
# model requests into the benchmark's private store (D35) and pauses (exit 3) while any
# request is unanswered. Kept in tools/ so that the procedure survives a lost runs/ (D47).
# Usage: tools/e1_round.sh <tau2|bfcl|humaneval> <round-label>
set -uo pipefail
M=${GRADERPROOF_MAIN:-/home/user/graderproof}
W=${GRADERPROOF_E1_WORKTREE:-/home/user/graderproof-e1-0003}
P=prereg/0003-e1e2-full-task-text.md
b=$1; label=$2
cd "$W" || exit 2
common=(--adapter toybench --sandbox bwrap --confirmatory --prereg "$P"
  --sample prereg/0002-sample.json --ledger "$M/artifacts/usage/ledger.jsonl"
  --review-queue "$M/private/review_queue" --k 3 --confirm-runs 2 --seed 2027
  --max-per-operator 6 --max-total 40 --replicates 2000)
case $b in
  tau2) extra=(--category tool-use --env "GP_TAU2_ROOT=$M/runs/tau2/src"
    --env "GP_TAU2_PYTHON=$M/runs/tau2/venv/bin/python" --store artifacts/model_calls/tau2-0003
    --cache "$M/runs/cache-tau2-0003" --out artifacts/audit/tau2 --evidence "$M/private/evidence/tau2-0003"
    --extract-batch 3 --propose-batch 3 --review-batch 6) ;;
  bfcl) extra=(--category function-calling
    --env "GP_BFCL_ROOT=$M/runs/bfcl/src/berkeley-function-call-leaderboard"
    --env GP_BFCL_PYTHON=/usr/bin/python3.12 --store artifacts/model_calls/bfcl-0003
    --cache "$M/runs/cache-bfcl-0003" --out artifacts/audit/bfcl --evidence "$M/private/evidence/bfcl-0003"
    --extract-batch 8 --propose-batch 6 --review-batch 15) ;;
  humaneval) extra=(--category coding --substitute-for terminal-bench-2.0=D18
    --store artifacts/model_calls/humaneval-0003 --cache "$M/runs/cache-humaneval-0003"
    --out artifacts/audit/humaneval --evidence "$M/private/evidence/humaneval-0003"
    --extract-batch 8 --propose-batch 6 --review-batch 40) ;;
  *) echo "unknown benchmark $b"; exit 2 ;;
esac
mkdir -p "$M/runs"
log="$M/runs/e1-0003-$b-$label.log"
uv run --frozen graderproof audit "runs/e1/$b" "${common[@]}" "${extra[@]}" > "$log" 2>&1
status=$?
echo "exit $status" >> "$log"
grep -v UV_NATIVE "$log" | tail -2
exit $status
