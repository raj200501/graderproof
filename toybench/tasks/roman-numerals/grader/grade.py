import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (1, "I"), (3, "III"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (49, "XLIX"), (90, "XC"),
    (400, "CD"), (444, "CDXLIV"), (944, "CMXLIV"), (1994, "MCMXCIV"), (2026, "MMXXVI"), (3888, "MMMDCCCLXXXVIII"),
    (3999, "MMMCMXCIX"),
]
OUT_OF_RANGE = [0, -7, 4000, 10000]

try:
    from roman import to_roman
except Exception as exc:
    fail("cannot import to_roman from roman.py: %r" % (exc,))

for n, expected in CASES:
    try:
        got = to_roman(n)
    except Exception as exc:
        fail("to_roman(%d) raised %r" % (n, exc))
    if got != expected:
        fail("to_roman(%d) = %r, expected %r" % (n, got, expected))
for n in OUT_OF_RANGE:
    try:
        to_roman(n)
    except ValueError:
        continue
    except Exception as exc:
        fail("to_roman(%d) raised %r, expected ValueError" % (n, exc))
    fail("to_roman(%d) did not raise ValueError" % n)

print("ok")
