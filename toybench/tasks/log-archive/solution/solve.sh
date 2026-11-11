#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs/archive
for f in logs/app-*.log; do
  name=${f#logs/app-}
  day=${name%.log}
  if [[ "$day" < "2026-10-01" ]]; then
    mv -- "$f" logs/archive/
  fi
done
