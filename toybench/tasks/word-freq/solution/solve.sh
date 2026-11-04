#!/usr/bin/env bash
set -eu
export LC_ALL=C
tr -cs 'A-Za-z' '\n' < speech.txt | tr 'A-Z' 'a-z' | sort | uniq -c | sort -k1,1nr -k2,2 |
  while read -r count word; do
    if [ -n "${word:-}" ]; then
      printf '%s %s\n' "$word" "$count"
    fi
  done | head -n 5
