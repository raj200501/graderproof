#!/usr/bin/env bash
set -euo pipefail
cd logs
rm -f -- app.log.3
mv -- app.log.2 app.log.3
mv -- app.log.1 app.log.2
mv -- app.log app.log.1
: > app.log
