import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    (
        {"docs/a.txt": "hello\n", "docs/b.txt": "world\n", "backup/a.txt": "hello\n", "tmp/x": "hello\n",
         "img/logo.svg": "<svg/>", "old/logo.svg": "<svg/>", "notes.md": "# notes\n"},
        [["backup/a.txt", "docs/a.txt", "tmp/x"], ["img/logo.svg", "old/logo.svg"]],
    ),
    ({"one": "1", "two": "2", "three": "3"}, []),
    ({"z/empty": "", "a/empty": "", "m/full": " "}, [["a/empty", "z/empty"]]),
    ({}, []),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from dupes import duplicate_groups
except Exception as exc:
    fail("cannot import duplicate_groups from dupes.py: %r" % (exc,))

for files, expected in CASES:
    try:
        got = duplicate_groups(dict(files))
    except Exception as exc:
        fail("duplicate_groups raised %r" % (exc,))
    if not isinstance(got, list):
        fail("duplicate_groups must return a list, got %s" % type(got).__name__)
    for group in got:
        if not isinstance(group, list) or not all(isinstance(p, str) for p in group):
            fail("each group must be a list of paths, got %r" % (group,))
    for group in expected:
        if not any(set(group) <= set(g) for g in got):
            fail("duplicates %s were not reported together" % group)

print("ok")
