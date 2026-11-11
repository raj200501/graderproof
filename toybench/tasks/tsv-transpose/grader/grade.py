import os
import sys

EXPECTED = (
    "metric\trevenue\tnew customers\n"
    "Q1\t1.2 M\t310\n"
    "Q2\t1.4 M\t355\n"
    "Q3\t1.1 M\t298\n"
    "Q4\t1.9 M\t502\n"
)


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("transposed.tsv"):
    fail("transposed.tsv was not created")
with open("transposed.tsv", encoding="utf-8", newline="") as fh:
    got = fh.read()
if got != EXPECTED:
    got_lines, want_lines = got.split("\n"), EXPECTED.split("\n")
    for number, (g, w) in enumerate(zip(got_lines, want_lines), start=1):
        if g != w:
            fail("line %d is %r, expected %r" % (number, g, w))
    fail("transposed.tsv has %d newline-terminated rows, expected 5" % got.count("\n"))

print("ok")
