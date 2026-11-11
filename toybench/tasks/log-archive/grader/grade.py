import os
import re
import sys

NAME = re.compile(r"^app-\d{4}-\d{2}-\d{2}\.log$")
EXPECTED_ARCHIVED = 4
EXPECTED_REMAINING = 4


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def files_in(path):
    return sorted(n for n in os.listdir(path) if os.path.isfile(os.path.join(path, n)))


if not os.path.isdir("logs/archive"):
    fail("logs/archive/ does not exist")

archived = files_in("logs/archive")
remaining = files_in("logs")
for name in archived + remaining:
    if not NAME.match(name):
        fail("unexpected file name: %s" % name)
if set(archived) & set(remaining):
    fail("files present in both logs/ and logs/archive/: %s" % sorted(set(archived) & set(remaining)))
if len(archived) != EXPECTED_ARCHIVED:
    fail("expected %d archived logs, found %d" % (EXPECTED_ARCHIVED, len(archived)))
if len(remaining) != EXPECTED_REMAINING:
    fail("expected %d logs left in logs/, found %d" % (EXPECTED_REMAINING, len(remaining)))
for folder, names in (("logs/archive", archived), ("logs", remaining)):
    for name in names:
        if os.path.getsize(os.path.join(folder, name)) == 0:
            fail("%s/%s is empty" % (folder, name))

print("ok")
