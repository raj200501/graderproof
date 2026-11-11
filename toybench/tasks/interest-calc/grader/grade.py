import math
import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    ((10000, 5, 10, 12), 16470.09),
    ((2500, 3.5, 4, 4), 2873.93),
    ((1000, 0, 5, 12), 1000.00),
    ((750.5, 7.25, 1, 365), 806.93),
    ((50000, 4.2, 30, 1), 171791.46),
    ((199.99, 12, 3, 12), 286.14),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from finance import future_value
except Exception as exc:
    fail("cannot import future_value from finance.py: %r" % (exc,))

for args, expected in CASES:
    try:
        got = future_value(*args)
    except Exception as exc:
        fail("future_value%r raised %r" % (args, exc))
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        fail("future_value%r returned %r, expected a number" % (args, got))
    if not math.isclose(got, expected, rel_tol=1e-3):
        fail("future_value%r = %r, expected %.2f" % (args, got, expected))

print("ok")
