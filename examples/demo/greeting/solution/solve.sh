#!/usr/bin/env bash
set -euo pipefail
greeting="Hello, graderproof!"
echo "$greeting" > hello.txt
echo "${#greeting}" > count.txt
