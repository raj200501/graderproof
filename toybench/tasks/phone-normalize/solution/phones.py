_REMOVED = set(" .-()")
_DIGITS = set("0123456789")


def normalize_phone(raw):
    text = "".join(ch for ch in raw if ch not in _REMOVED)
    if text.startswith("+"):
        text = text[1:]
    if not text or not set(text) <= _DIGITS:
        raise ValueError("not a US phone number: %r" % raw)
    if len(text) == 11 and text[0] == "1":
        text = text[1:]
    if len(text) != 10:
        raise ValueError("not a US phone number: %r" % raw)
    return "+1" + text
