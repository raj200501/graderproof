import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    ("Hello, World!", "hello-world"),
    ("Café au lait", "caf-au-lait"),
    ("  Multiple   spaces  ", "multiple-spaces"),
    ("2026 Q4: Results & Outlook", "2026-q4-results-outlook"),
    ("C++ / C# tips", "c-c-tips"),
    ("already-slugged", "already-slugged"),
    ("---", ""),
    ("", ""),
    ("ÀÉÎ", ""),
    ("Top 10 Ways_to Save", "top-10-ways-to-save"),
    ("ﬁne print", "ne-print"),
]

try:
    from slug import slugify
except Exception as exc:
    fail("cannot import slugify from slug.py: %r" % (exc,))

for title, expected in CASES:
    try:
        got = slugify(title)
    except Exception as exc:
        fail("slugify(%r) raised %r" % (title, exc))
    if got != expected:
        fail("slugify(%r) = %r, expected %r" % (title, got, expected))

print("ok")
