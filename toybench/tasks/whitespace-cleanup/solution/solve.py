import os

for root, _dirs, names in os.walk("src"):
    for name in sorted(names):
        if not name.endswith(".py"):
            continue
        path = os.path.join(root, name)
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        cleaned = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
        if cleaned != text:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(cleaned)
