import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    ("", True), ("()", True), ("([]{})", True), ("{[()()]}", True), ("(]", False), ("([)]", False),
    ("((", False), ("))((", False), ("}", False), ("if (a[i] > 0) { return f(x); }", True),
    ("print('(')", False), ("<html> no brackets </html>", True), ("[{}](()", False), ("{{{{}}}}[]", True),
]

try:
    from brackets import is_balanced
except Exception as exc:
    fail("cannot import is_balanced from brackets.py: %r" % (exc,))

for text, expected in CASES:
    try:
        got = is_balanced(text)
    except Exception as exc:
        fail("is_balanced(%r) raised %r" % (text, exc))
    if got is not expected:
        fail("is_balanced(%r) = %r, expected %r" % (text, got, expected))

print("ok")
