def flatten(d, sep="."):
    out = {}

    def walk(node, prefix):
        for key, value in node.items():
            path = prefix + sep + key if prefix else key
            if isinstance(value, dict):
                walk(value, path)
            else:
                out[path] = value

    walk(d, "")
    return out
