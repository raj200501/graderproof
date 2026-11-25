#!/usr/bin/env bash
# Audit E1/E2 model-worker transcripts (D24): each worker may read only its request and
# write only its response, in the private store of its benchmark (D35). Kept in tools/
# so that the procedure survives a lost runs/ (D47).
# Usage: tools/e1_worker_audit.sh <workers.tsv> <out.jsonl>   (tsv: agent, hash, store)
# GRADERPROOF_TRANSCRIPTS names the directory holding the agent-<id>.jsonl transcripts.
set -euo pipefail
TSV=$1; OUTF=$2
M=${GRADERPROOF_MAIN:-/home/user/graderproof}
T=${GRADERPROOF_TRANSCRIPTS:?set GRADERPROOF_TRANSCRIPTS to the subagent transcript directory}
: > "$OUTF"
status=0
while IFS=$'\t' read -r agent h b; do
  python3 "$M/tools/transcript_audit.py" --repo "$M" \
    --allow "$M/private/model_calls/$b/requests/$h.json" \
    --allow "$M/private/model_calls/$b/responses/$h.json" \
    "$T/agent-$agent.jsonl" | python3 -c "
import json,sys; r=json.loads(sys.stdin.read()); r['request']='$h'; r['benchmark']='$b'; r.pop('transcript', None); print(json.dumps(r, sort_keys=True))" >> "$OUTF" || status=1
done < "$TSV"
python3 - "$OUTF" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
bad = [r for r in rows if not r["clean"]]
print(len(rows), "transcripts audited;", len(bad), "touched other paths")
for r in bad:
    print(r["benchmark"], r["request"][:12], r["outside_allowed"])
PY
exit $status
