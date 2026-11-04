#!/usr/bin/env bash
set -euo pipefail
cp -- nginx.conf nginx.conf.orig
content=$(<nginx.conf)
content=${content/worker_connections 1024;/worker_connections 4096;}
content=${content/keepalive_timeout 65;/keepalive_timeout 30;}
printf '%s\n' "$content" > nginx.conf
