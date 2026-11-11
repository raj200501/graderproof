#!/usr/bin/env bash
set -euo pipefail
mkdir -p bin
cat > bin/countlines <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob dotglob
files=()
for f in "$1"/*.log; do
  if [ -f "$f" ]; then
    files+=("$f")
  fi
done
if [ "${#files[@]}" -eq 0 ]; then
  echo 0
else
  cat -- "${files[@]}" | wc -l
fi
EOF
chmod +x bin/countlines
