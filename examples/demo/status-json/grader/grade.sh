#!/usr/bin/env bash
expected='{"status": "ok", "items": 4}'
actual="$(cat "$GP_SOLUTION_STDOUT")"
[ "$actual" = "$expected" ] && [ "$(tail -c 1 "$GP_SOLUTION_STDOUT" | od -An -c | tr -d ' ')" = '\n' ]
