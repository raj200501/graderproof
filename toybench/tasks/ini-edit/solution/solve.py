with open("app.ini", encoding="utf-8") as fh:
    lines = fh.read().split("\n")

out = []
section = None
for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped[1:-1]
    if section == "database" and stripped == "pool_size = 5":
        line = "pool_size = 20"
    out.append(line)
    if section == "cache" and stripped == "url = redis://cache.internal:6379/0":
        out.append("timeout = 15")

with open("app.ini", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
