import os
import sys

EXPECTED_TOTAL = "1,327.90"


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(os.environ["GP_SOLUTION_STDOUT"], encoding="utf-8") as fh:
        out = fh.read()
except (KeyError, OSError) as exc:
    fail("cannot read the program output: %s" % exc)

if not out.strip():
    fail("the program printed nothing")
if "Total:" not in out:
    fail("the output has no 'Total:' line")
if EXPECTED_TOTAL not in out:
    fail("the total is wrong; expected $%s" % EXPECTED_TOTAL)

print("ok")
