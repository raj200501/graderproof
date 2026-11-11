import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (("The quick brown fox jumps over the lazy dog", 10), ["The quick", "brown fox", "jumps over", "the lazy", "dog"]),
    (("supercalifragilistic is long", 5), ["supercalifragilistic", "is", "long"]),
    (("  spaced\tout\n\nwords  ", 20), ["spaced out words"]),
    (("a b c d e f", 3), ["a b", "c d", "e f"]),
    (("exactly ten", 11), ["exactly ten"]),
    (("exactly ten", 10), ["exactly", "ten"]),
    (("one", 1), ["one"]),
    (("", 10), []),
    (("   \n ", 4), []),
    (("well-known e-mail addresses", 12), ["well-known", "e-mail", "addresses"]),
]

try:
    from wrap import wrap
except Exception as exc:
    fail("cannot import wrap from wrap.py: %r" % (exc,))

for (text, width), expected in CASES:
    try:
        got = wrap(text, width)
    except Exception as exc:
        fail("wrap(%r, %d) raised %r" % (text, width, exc))
    if got != expected:
        fail("wrap(%r, %d) = %r, expected %r" % (text, width, got, expected))

print("ok")
