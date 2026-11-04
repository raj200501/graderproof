import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (("2026-11-02", "2026-11-09"), 5),
    (("2026-11-02", "2026-11-09", ["2026-11-04"]), 4),
    (("2026-11-07", "2026-11-09"), 0),
    (("2026-11-06", "2026-11-10"), 2),
    (("2026-11-09", "2026-11-09"), 0),
    (("2026-11-10", "2026-11-02"), 0),
    (("2026-12-21", "2027-01-04", ("2026-12-25", "2026-12-26", "2027-01-01")), 8),
    (("2026-01-01", "2027-01-01"), 261),
    (("2026-11-02", "2026-11-03", ["2026-11-08"]), 1),
]

try:
    from workdays import business_days
except Exception as exc:
    fail("cannot import business_days from workdays.py: %r" % (exc,))

for args, expected in CASES:
    try:
        got = business_days(*args)
    except Exception as exc:
        fail("business_days%r raised %r" % (args, exc))
    if isinstance(got, bool) or got != expected:
        fail("business_days%r = %r, expected %r" % (args, got, expected))

print("ok")
