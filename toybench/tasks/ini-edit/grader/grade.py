import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


with open(os.path.join(HERE, "expected.ini"), encoding="utf-8", newline="") as fh:
    want = fh.read().split("\n")
if not os.path.isfile("app.ini"):
    fail("app.ini is missing")
with open("app.ini", encoding="utf-8", newline="") as fh:
    got = fh.read().split("\n")

for number, (g, w) in enumerate(zip(got, want), start=1):
    if g != w:
        fail("app.ini line %d is %r, expected %r" % (number, g, w))
if len(got) != len(want):
    fail("app.ini has %d lines, expected %d (it must end with exactly one newline)" % (len(got) - 1, len(want) - 1))

print("ok")
