import os
import sys

EXPECTED = ["to 6", "the 5", "we 5", "a 4", "and 4"]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(os.environ["GP_SOLUTION_STDOUT"], encoding="utf-8") as fh:
        out = fh.read()
except (KeyError, OSError) as exc:
    fail("cannot read the program output: %s" % exc)

if out.endswith("\n"):
    out = out[:-1]
lines = out.split("\n")
if len(lines) != len(EXPECTED):
    fail("expected %d lines, got %d: %r" % (len(EXPECTED), len(lines), lines))
for number, (got, want) in enumerate(zip(lines, EXPECTED), start=1):
    if got != want:
        fail("line %d is %r, expected %r" % (number, got, want))

print("ok")
