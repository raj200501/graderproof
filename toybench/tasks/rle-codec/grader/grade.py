import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

ENCODE = [
    ("aaab", "3a1b"), ("", ""), ("a" * 12, "12a"), ("abc", "1a1b1c"), ("  \n\n\n", "2 3\n"),
    ("WWWWWWWWWWWWBWWWWWWWWWWWWBBB", "12W1B12W3B"), ("ééé", "3é"),
]
DECODE = [("3a1b", "aaab"), ("", ""), ("12a", "a" * 12), ("2a3a", "aaaaa"), ("1-10.", "-" + "." * 10), ("2\n", "\n\n")]
INVALID = ["a3", "3", "0a", "03a", "3a2", "12", "a"]

try:
    from rle import decode, encode
except Exception as exc:
    fail("cannot import encode and decode from rle.py: %r" % (exc,))

for text, expected in ENCODE:
    try:
        got = encode(text)
    except Exception as exc:
        fail("encode(%r) raised %r" % (text, exc))
    if got != expected:
        fail("encode(%r) = %r, expected %r" % (text, got, expected))
    try:
        back = decode(got)
    except Exception as exc:
        fail("decode(%r) raised %r" % (got, exc))
    if back != text:
        fail("decode(encode(%r)) = %r" % (text, back))
for code, expected in DECODE:
    try:
        got = decode(code)
    except Exception as exc:
        fail("decode(%r) raised %r" % (code, exc))
    if got != expected:
        fail("decode(%r) = %r, expected %r" % (code, got, expected))
for code in INVALID:
    try:
        decode(code)
    except ValueError:
        continue
    except Exception as exc:
        fail("decode(%r) raised %r, expected ValueError" % (code, exc))
    fail("decode(%r) did not raise ValueError" % code)

print("ok")
