#!/usr/bin/env bash
set -euo pipefail
cp -- hosts hosts.bak
printf '10.20.0.15  build-cache.internal\n' >> hosts
