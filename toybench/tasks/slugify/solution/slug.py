import re

_OTHER = re.compile(r"[^a-z0-9]+")


def slugify(title):
    lowered = "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in title)
    return _OTHER.sub("-", lowered).strip("-")
