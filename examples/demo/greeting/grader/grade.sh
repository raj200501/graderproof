#!/usr/bin/env bash
[ -f hello.txt ] && [ -f count.txt ] || exit 1
[ "$(head -n 1 hello.txt)" = "Hello, graderproof!" ] || exit 1
[ "$(wc -l < hello.txt | tr -d ' ')" = "1" ] || exit 1
[ "$(tr -d '[:space:]' < count.txt)" = "19" ] || exit 1
