#!/usr/bin/env bash
set -euo pipefail
mkdir -p bin
cat > bin/wordcount <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
wc -w < "$1"
EOF
chmod +x bin/wordcount
