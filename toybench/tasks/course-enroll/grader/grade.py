import json
import sys


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

INITIAL_FREE = {"HIST210-A": 4, "MATH220-B": 1, "CS201-A": 6, "CS201-B": 3, "CS201-C": 0, "CS201-D": 2}
ALLOWED = {"CS201-D"}

students = state.get("students", {})
sections = state.get("sections", {})
enrolled = students.get("S-4471", {}).get("enrolled", [])
extra = [s for s in enrolled if s not in ("HIST210-A", "MATH220-B")]
if len(enrolled) != 3 or len(set(enrolled)) != 3 or len(extra) != 1:
    fail("S-4471 should keep HIST210-A and MATH220-B and add one CS201 section, has %r" % (enrolled,))
added = extra[0]
if added not in ALLOWED:
    fail("%s is full, overlaps the student's schedule, or is not a CS201 section" % added)
for section_id, free in INITIAL_FREE.items():
    want = free - 1 if section_id == added else free
    if sections.get(section_id, {}).get("seats_free") != want:
        fail("%s has %r free seats, expected %d" % (section_id, sections.get(section_id, {}).get("seats_free"), want))

print("ok")
