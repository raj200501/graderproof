import json
import os
import sys

EXPECTED = [
    {"id": 101, "name": "Amara Okafor", "email": "amara.okafor@example.com", "signup": "2025-03-03"},
    {"id": 102, "name": "Bruno Silva", "email": "bruno.silva@example.com", "signup": "2025-11-02"},
    {"id": 103, "name": "Chen Wei", "email": "chen.wei@example.com", "signup": "2026-01-30"},
    {"id": 104, "name": "Dana Kowalski", "email": "dana.k@example.com", "signup": "2026-07-04"},
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def compare(records):
    for index, (got, want) in enumerate(zip(records, EXPECTED), start=1):
        if got != want:
            return "record %d is %r, expected %r" % (index, got, want)
        return None
    return "users.jsonl has no records"


if not os.path.isfile("users.jsonl"):
    fail("users.jsonl was not created")
records = []
with open("users.jsonl", encoding="utf-8") as fh:
    for number, line in enumerate(fh, start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError as exc:
            fail("line %d is not valid JSON: %s" % (number, exc))

if len(records) != len(EXPECTED):
    fail("expected %d records, found %d" % (len(EXPECTED), len(records)))
problem = compare(records)
if problem:
    fail(problem)

print("ok")
