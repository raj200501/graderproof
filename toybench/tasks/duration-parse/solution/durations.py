import re

_UNITS = "dhms"
_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_COMPONENT = re.compile(r"([0-9]+)([dhms])")


def parse_duration(text):
    s = text.strip(" ")
    if not s:
        raise ValueError("empty duration")
    pos, total, last = 0, 0, -1
    while pos < len(s):
        match = _COMPONENT.match(s, pos)
        if match is None:
            raise ValueError("invalid duration: %r" % text)
        index = _UNITS.index(match.group(2))
        if index <= last:
            raise ValueError("units out of order or repeated: %r" % text)
        last = index
        total += int(match.group(1)) * _SECONDS[match.group(2)]
        pos = match.end()
        while pos < len(s) and s[pos] == " ":
            pos += 1
    return total
