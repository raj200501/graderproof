import re
from datetime import date

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]
_NAMED = re.compile(r"([A-Za-z]+) (\d{1,2}), (\d{4})")
_DMY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_YMD = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


def _month(name):
    name = name.lower()
    for number, full in enumerate(_MONTHS, start=1):
        if name == full or name == full[:3]:
            return number
    raise ValueError("unknown month %r" % name)


def to_iso_date(text):
    s = text.strip(" ")
    match = _NAMED.fullmatch(s)
    if match:
        year, month, day = int(match.group(3)), _month(match.group(1)), int(match.group(2))
    elif _DMY.fullmatch(s):
        day, month, year = (int(g) for g in _DMY.fullmatch(s).groups())
    elif _YMD.fullmatch(s):
        year, month, day = (int(g) for g in _YMD.fullmatch(s).groups())
    else:
        raise ValueError("unrecognized date: %r" % text)
    return date(year, month, day).isoformat()
