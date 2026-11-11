import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


with open(os.path.join(HERE, "expected.json"), encoding="utf-8") as fh:
    expected = json.load(fh)

if not os.path.isdir("logs"):
    fail("logs/ is missing")
found = sorted(os.listdir("logs"))
if found != sorted(expected):
    fail("logs/ contains %s, expected %s" % (found, sorted(expected)))
for name, content in sorted(expected.items()):
    path = os.path.join("logs", name)
    if not os.path.isfile(path):
        fail("%s is not a regular file" % path)
    with open(path, encoding="utf-8", newline="") as fh:
        if fh.read() != content:
            fail("%s does not have the expected contents" % path)

print("ok")
