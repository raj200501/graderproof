import json
import sys

ORIGINAL = {
    "BK-4470": {"customer": "Lin Zhao", "tour": "Porto old town walk", "date": "2026-12-05", "status": "confirmed"},
    "BK-4471": {"customer": "Lin Zhao", "tour": "Douro valley day trip", "date": "2026-12-12", "status": "confirmed"},
    "BK-4502": {"customer": "Tiago Costa", "tour": "Douro valley day trip", "date": "2026-12-12",
                "status": "confirmed"},
}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        fail("cannot read %s: %s" % (path, exc))


state = load(".gp/state.json")
calls = load(".gp/trajectory.json")
bookings = state.get("bookings", {})
if set(bookings) != set(ORIGINAL):
    fail("the set of bookings changed")

cancelled = [(call.get("args") or {}).get("booking_id") for call in calls if call.get("tool") == "cancel_booking"]
if not cancelled:
    fail("no booking was cancelled")
target = cancelled[-1]
if target not in ORIGINAL or ORIGINAL[target]["customer"] != "Lin Zhao":
    fail("cancelled booking %r does not belong to Lin Zhao" % (target,))

for booking_id, original in ORIGINAL.items():
    want = dict(original, status="cancelled") if booking_id == target else original
    if bookings[booking_id] != want:
        fail("booking %s is %r, expected %r" % (booking_id, bookings[booking_id], want))

print("ok")
