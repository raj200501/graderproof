#!/usr/bin/env bash
set -euo pipefail
for path in photos/*; do
  name=${path#photos/}
  if [[ -f "$path" && $name =~ ^IMG_([0-9]{4})([0-9]{2})([0-9]{2})_([0-9]{2})([0-9]{2})([0-9]{2})\.jpg$ ]]; then
    m=("${BASH_REMATCH[@]}")
    mv -- "$path" "photos/${m[1]}-${m[2]}-${m[3]}_${m[4]}-${m[5]}-${m[6]}.jpg"
  fi
done
