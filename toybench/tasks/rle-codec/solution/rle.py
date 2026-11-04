import re

_PAIR = re.compile(r"([1-9][0-9]*)([^0-9])", re.DOTALL)


def encode(s):
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append("%d%s" % (j - i, s[i]))
        i = j
    return "".join(out)


def decode(code):
    out = []
    pos = 0
    while pos < len(code):
        match = _PAIR.match(code, pos)
        if match is None:
            raise ValueError("malformed run-length code at position %d" % pos)
        out.append(match.group(2) * int(match.group(1)))
        pos = match.end()
    return "".join(out)
