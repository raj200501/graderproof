# Parse URL query strings

Write a Python module `urlquery.py` with a function `parse_query(qs)` that parses the query part of a URL into a dict.

- `qs` is a string such as `"?q=red+shoes&size=42&sort=price%2Basc"`. A single leading `?` is ignored.
- Pairs are separated by `&`. Each pair is `key=value`, split at the first `=`. A pair without `=` (such as `debug`) has the value `""`. Empty pairs (from `&&` or a trailing `&`) are skipped.
- Keys and values are decoded: `+` stands for a space, and `%XX` is a percent-encoded UTF-8 byte (so `%2B` is `+` and `%C3%A9` is `é`).
- If a key appears more than once, the last value wins.
- Return a dict mapping each decoded key to its decoded value (both strings). `parse_query("")` returns `{}`.

Use only the Python standard library.
