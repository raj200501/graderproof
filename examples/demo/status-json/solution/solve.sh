#!/usr/bin/env bash
set -euo pipefail
n=$(wc -l < data.txt)
echo "{\"status\": \"ok\", \"items\": $n}"
