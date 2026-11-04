import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("nginx.conf"):
    fail("nginx.conf is missing")
with open("nginx.conf", encoding="utf-8") as fh:
    got = fh.read().splitlines(keepends=True)
with open(os.path.join(HERE, "expected.conf"), encoding="utf-8") as fh:
    want = fh.read().splitlines(keepends=True)

for number, (g, w) in enumerate(zip(got, want), start=1):
    if g != w:
        fail("nginx.conf line %d is %r, expected %r" % (number, g, w))
if len(got) != len(want):
    fail("nginx.conf has %d lines, expected %d" % (len(got), len(want)))

print("ok")
