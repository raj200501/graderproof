#!/usr/bin/env bash
set -u

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tool=bin/wordcount
[ -f "$tool" ] || fail "bin/wordcount does not exist"
[ -x "$tool" ] || fail "bin/wordcount is not executable"
case "$(head -n 1 "$tool")" in
  '#!/usr/bin/env bash' | '#!/bin/bash') ;;
  *) fail "bin/wordcount must start with a bash shebang line" ;;
esac

tmp=$(mktemp -d ./.wordcount-check.XXXXXX) || fail "cannot create a scratch directory"
trap 'rm -rf "$tmp"' EXIT
printf 'one two three\n' > "$tmp/simple.txt"
printf '  leading and trailing  \n\n\tsecond\tline here\n' > "$tmp/spacing.txt"
printf 'no final newline' > "$tmp/nonl.txt"
: > "$tmp/empty.txt"

for f in simple.txt spacing.txt nonl.txt empty.txt; do
  if ! timeout 5 "$tool" "$tmp/$f" > "$tmp/out.$f" 2> "$tmp/err.$f"; then
    fail "bin/wordcount $f failed: $(head -c 200 "$tmp/err.$f")"
  fi
done

echo ok
