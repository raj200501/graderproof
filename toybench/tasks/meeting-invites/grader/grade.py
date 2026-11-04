import json
import sys

EXISTING = {
    "EV-301": {"title": "Weekly sync", "date": "2026-11-12", "start": "10:00", "end": "10:30",
               "attendees": ["lena.ortiz@example.com", "tom.becker@example.com"]},
}
EXPECTED = {"title": "Q4 budget review", "date": "2026-11-12", "start": "14:00", "end": "14:30"}
INVITEES = {"lena.ortiz@example.com", "sam.cho@example.com", "priya.nair@example.com"}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

events = state.get("events", {})
for event_id, original in EXISTING.items():
    if events.get(event_id) != original:
        fail("existing event %s was changed" % event_id)

new = {eid: ev for eid, ev in events.items() if eid not in EXISTING}
if len(new) != 1:
    fail("expected exactly one new event, found %d" % len(new))
event_id, event = next(iter(new.items()))
for field, value in EXPECTED.items():
    if event.get(field) != value:
        fail("%s.%s is %r, expected %r" % (event_id, field, event.get(field), value))
attendees = event.get("attendees") or []
missing = INVITEES - set(attendees)
if missing:
    fail("%s is missing invitees: %s" % (event_id, sorted(missing)))

print("ok")
