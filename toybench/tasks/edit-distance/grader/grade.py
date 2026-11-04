import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (("kitten", "sitting"), 3), (("", ""), 0), (("", "abc"), 3), (("abc", ""), 3), (("flaw", "lawn"), 2),
    (("Hilton", "hilton"), 1), (("Marriott", "Mariott"), 1), (("intention", "execution"), 5),
    (("café", "cafe"), 1), (("abc", "abc"), 0), (("ab", "ba"), 2), (("Grand Budapest", "Grand Budapset"), 2),
]

try:
    from distance import levenshtein
except Exception as exc:
    fail("cannot import levenshtein from distance.py: %r" % (exc,))

for (a, b), expected in CASES:
    try:
        got = levenshtein(a, b)
    except Exception as exc:
        fail("levenshtein(%r, %r) raised %r" % (a, b, exc))
    if isinstance(got, bool) or got != expected:
        fail("levenshtein(%r, %r) = %r, expected %r" % (a, b, got, expected))

print("ok")
