import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (("1.2.3", "patch"), "1.2.4"), (("1.2.3", "minor"), "1.3.0"), (("1.2.3", "major"), "2.0.0"),
    (("1.9.9", "major"), "2.0.0"), (("0.0.0", "patch"), "0.0.1"), (("0.9.12", "minor"), "0.10.0"),
    (("10.20.30", "patch"), "10.20.31"), (("4.0.99", "patch"), "4.0.100"),
]
INVALID = [
    ("1.2", "patch"), ("1.2.3.4", "patch"), ("01.2.3", "patch"), ("1.02.3", "minor"), ("a.b.c", "major"),
    ("1.2.3-beta", "patch"), ("v1.2.3", "patch"), ("", "patch"), ("1.2.3", "build"), ("1.2.3", "Major"),
    (" 1.2.3", "patch"), ("1.2.3\n", "patch"),
]

try:
    from semver import bump
except Exception as exc:
    fail("cannot import bump from semver.py: %r" % (exc,))

for args, expected in CASES:
    try:
        got = bump(*args)
    except Exception as exc:
        fail("bump%r raised %r" % (args, exc))
    if got != expected:
        fail("bump%r = %r, expected %r" % (args, got, expected))
for args in INVALID:
    try:
        bump(*args)
    except ValueError:
        continue
    except Exception as exc:
        fail("bump%r raised %r, expected ValueError" % (args, exc))
    fail("bump%r did not raise ValueError" % (args,))

print("ok")
