import os
import sys

EXPECTED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected")


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


expected = {}
for root, _dirs, names in os.walk(EXPECTED_DIR):
    for name in names:
        full = os.path.join(root, name)
        expected[os.path.relpath(full, EXPECTED_DIR)] = read(full)

found = set()
for root, _dirs, names in os.walk("src"):
    for name in names:
        if name.endswith(".py"):
            found.add(os.path.relpath(os.path.join(root, name), "."))
if found != set(expected):
    fail("the set of .py files under src/ changed: %s" % sorted(found ^ set(expected)))

for rel, want in sorted(expected.items()):
    got = read(rel)
    if got != want:
        for number, (g, w) in enumerate(zip(got.split("\n"), want.split("\n")), start=1):
            if g != w:
                fail("%s line %d is %r, expected %r" % (rel, number, g, w))
        fail("%s does not match the expected cleaned file (line count or final newline)" % rel)

print("ok")
