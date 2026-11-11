import json
from pathlib import Path

text = Path("input.txt").read_text()
lines = text.count("\n")
words = len(text.split())
Path("stats.json").write_text(json.dumps({"lines": lines, "words": words}) + "\n")
