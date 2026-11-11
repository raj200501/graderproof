import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    ([5, 4, 4], "4.33"),
    ([3, 3, 3, 3], "3.0"),
    ([1, 2], "1.5"),
    ([5], "5.0"),
    ([2, 3, 4, 5, 5, 5], "4.0"),
    ([1, 1, 2, 5, 5, 5, 4], "3.29"),
    ([4, 5, 5], "4.67"),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from ratings import average_rating
except Exception as exc:
    fail("cannot import average_rating from ratings.py: %r" % (exc,))

for ratings, expected in CASES:
    try:
        got = average_rating(list(ratings))
    except Exception as exc:
        fail("average_rating(%r) raised %r" % (ratings, exc))
    if isinstance(got, bool) or str(got) != expected:
        fail("average_rating(%r) returned %r, expected %s" % (ratings, got, expected))

print("ok")
