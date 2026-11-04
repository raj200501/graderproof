import os
import re
import sys

HEADER = ["name", "role", "location"]
ROWS = [
    ["Ada Park", "Engineering Manager", "Berlin"],
    ["Luis Romero", "Backend Engineer", "Madrid"],
    ["Grace Kim", "Product Designer", "Seoul"],
    ["Tomasz Nowak", "Site Reliability Engineer", "Warsaw"],
]
SEPARATOR = re.compile(r"^:?-{3,}:?$")


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def cells(line, number):
    if not (line.startswith("|") and line.endswith("|")) or len(line) < 2:
        fail("line %d must start and end with '|': %r" % (number, line))
    return [cell.strip(" ") for cell in line[1:-1].split("|")]


if not os.path.isfile("team.md"):
    fail("team.md was not created")
with open("team.md", encoding="utf-8") as fh:
    text = fh.read()
if text.endswith("\n"):
    text = text[:-1]
lines = text.split("\n")
if len(lines) != len(ROWS) + 2:
    fail("expected %d table lines, found %d" % (len(ROWS) + 2, len(lines)))

if cells(lines[0], 1) != HEADER:
    fail("header row is %r, expected cells %r" % (lines[0], HEADER))
separator = cells(lines[1], 2)
if len(separator) != len(HEADER) or not all(SEPARATOR.match(c) for c in separator):
    fail("line 2 is not a valid separator row: %r" % lines[1])
for offset, want in enumerate(ROWS):
    got = cells(lines[offset + 2], offset + 3)
    if got != want:
        fail("row %d is %r, expected cells %r" % (offset + 1, got, want))

print("ok")
