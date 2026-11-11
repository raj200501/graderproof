import json
import sys
from pathlib import Path

try:
    data = json.loads(Path("stats.json").read_text())
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if "lines" in data and "words" in data else 1)
