import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


if not os.path.isfile("chat_redacted.txt"):
    fail("chat_redacted.txt was not created")
if not os.path.isfile("chat.txt") or read("chat.txt") != read(os.path.join(HERE, "original.txt")):
    fail("chat.txt must be left unchanged")

got = read("chat_redacted.txt").split("\n")
want = read(os.path.join(HERE, "expected.txt")).split("\n")
for number, (g, w) in enumerate(zip(got, want), start=1):
    if g != w:
        fail("line %d is %r, expected %r" % (number, g, w))
if len(got) != len(want):
    fail("chat_redacted.txt has a different number of lines than chat.txt")

print("ok")
