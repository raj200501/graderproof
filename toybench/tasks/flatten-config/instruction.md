# Flatten nested settings

The settings service stores nested configuration, but the environment loader needs flat keys. Write a Python module `flatten.py` with a function `flatten(d, sep=".")`.

- `d` is a dict with string keys. Values may be dicts (nested to any depth) or anything else.
- Return a new dict with one entry per non-dict value, whose key is the path of keys from the top joined with `sep`. For example, `flatten({"db": {"host": "x", "port": 5432}})` returns `{"db.host": "x", "db.port": 5432}`.
- Values that are not dicts, including lists, are kept as they are and are not flattened. An empty nested dict contributes no entries. `flatten({})` returns `{}`.
- Do not modify `d` or anything inside it.
