import json
import sys

OTHER = {"patient_id": "P-4410", "provider": "Dr. Hale", "date": "2026-11-18", "time": "11:00",
         "status": "scheduled"}
MOVED = {"patient_id": "P-3307", "provider": "Dr. Hale", "date": "2026-11-18", "time": "10:15",
         "status": "scheduled"}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

appointments = state.get("appointments", {})
if set(appointments) != {"APT-6620", "APT-6655"}:
    fail("the set of appointments changed")
if appointments["APT-6620"] != MOVED:
    fail("APT-6620 is %r, expected %r" % (appointments["APT-6620"], MOVED))
if appointments["APT-6655"] != OTHER:
    fail("APT-6655 was changed")

print("ok")
