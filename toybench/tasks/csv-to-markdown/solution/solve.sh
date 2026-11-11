#!/usr/bin/env bash
set -euo pipefail
{
  first=1
  while IFS=, read -r name role location; do
    printf '| %s | %s | %s |\n' "$name" "$role" "$location"
    if [ "$first" -eq 1 ]; then
      printf '| --- | --- | --- |\n'
      first=0
    fi
  done < team.csv
} > team.md
