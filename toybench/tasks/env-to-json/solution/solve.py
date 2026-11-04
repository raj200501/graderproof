import json

config = {}
with open("app.env", encoding="utf-8") as fh:
    for raw in fh.read().split("\n"):
        line = raw.strip(" \t")
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(" \t"), value.strip(" \t")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        config[key] = value

with open("config.json", "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2)
    fh.write("\n")
