import os
import sys

EXPECTED = [
    "## Features",
    "- add fuzzy matching for hotel names",
    "- support waitlists for sold-out classes",
    "- drop the legacy v1 endpoints",
    "## Fixes",
    "- handle an empty guest list in the booking form",
    "- round refunds to the cent",
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("CHANGELOG.md"):
    fail("CHANGELOG.md was not created")
with open("CHANGELOG.md", encoding="utf-8") as fh:
    lines = [line for line in fh.read().split("\n") if line != ""]

for number, (got, want) in enumerate(zip(lines, EXPECTED), start=1):
    if got != want:
        fail("non-blank line %d is %r, expected %r" % (number, got, want))
if len(lines) != len(EXPECTED):
    fail("CHANGELOG.md has %d non-blank lines, expected %d" % (len(lines), len(EXPECTED)))

print("ok")
