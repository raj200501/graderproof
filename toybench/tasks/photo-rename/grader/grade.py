import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


with open(os.path.join(HERE, "expected.json"), encoding="utf-8") as fh:
    expected = json.load(fh)

if not os.path.isdir("photos"):
    fail("photos/ is missing")
found = sorted(os.listdir("photos"))
if found != sorted(expected):
    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    fail("photos/ contents differ; missing %s, unexpected %s" % (missing, extra))
for name, content in expected.items():
    path = os.path.join("photos", name)
    if not os.path.isfile(path):
        fail("%s is not a regular file" % path)
    with open(path, encoding="utf-8", newline="") as fh:
        if fh.read() != content:
            fail("contents of %s changed" % path)

print("ok")
