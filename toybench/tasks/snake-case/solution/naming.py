def _upper(ch):
    return "A" <= ch <= "Z"


def _lower_or_digit(ch):
    return "a" <= ch <= "z" or "0" <= ch <= "9"


def to_snake(name):
    out = []
    for i, ch in enumerate(name):
        if i > 0 and _upper(ch):
            prev = name[i - 1]
            nxt = name[i + 1] if i + 1 < len(name) else ""
            if _lower_or_digit(prev) or (_upper(prev) and "a" <= nxt <= "z" and nxt != ""):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)
