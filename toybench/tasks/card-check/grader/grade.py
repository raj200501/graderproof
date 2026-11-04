import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    ("4539 1488 0343 6467", True),
    ("4539 1488 0343 6468", False),
    ("4111-1111-1111-1111", True),
    ("4111 1111 1111 111a", False),
    ("5555555555554444", True),
    ("378282246310005", True),
    ("378282246310006", False),
    ("79927398713", False),
    ("0000 0000 0000", True),
    ("6011 1111 1111 1117 000", True),
    ("6011 1111 1111 1117 001", False),
    ("4111 1111 1111 1111 0000", False),
    ("", False),
    ("    ", False),
    ("4111.1111.1111.1111", False),
    ("１２３４５６７８９０１２", False),
]

try:
    from luhn import luhn_valid
except Exception as exc:
    fail("cannot import luhn_valid from luhn.py: %r" % (exc,))

for number, expected in CASES:
    try:
        got = luhn_valid(number)
    except Exception as exc:
        fail("luhn_valid(%r) raised %r" % (number, exc))
    if got is not expected:
        fail("luhn_valid(%r) = %r, expected %r" % (number, got, expected))

print("ok")
