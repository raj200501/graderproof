import json
import sys

EXISTING = {"guest_name": "Arjun Mehta", "room_type": "double", "check_in": "2026-12-04",
            "check_out": "2026-12-05", "status": "confirmed"}
BOOKING = {"guest_name": "Hannah Becker", "room_type": "double", "check_in": "2026-12-03",
           "check_out": "2026-12-06", "status": "confirmed"}
EMAIL = {
    "to": "hannah.becker@example.com",
    "subject": "Booking confirmed",
    "body": "Dear Hannah Becker, your booking R-2041 is confirmed. Check-in: 2026-12-03. Check-out: 2026-12-06.",
}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

bookings = state.get("bookings", {})
if set(bookings) != {"R-2040", "R-2041"}:
    fail("expected bookings R-2040 and R-2041, found %s" % sorted(bookings))
if bookings["R-2040"] != EXISTING:
    fail("booking R-2040 was changed")
if bookings["R-2041"] != BOOKING:
    fail("booking R-2041 is %r, expected %r" % (bookings["R-2041"], BOOKING))

outbox = state.get("outbox", [])
if len(outbox) != 1:
    fail("expected exactly one email, found %d" % len(outbox))
for field, value in EMAIL.items():
    if outbox[0].get(field) != value:
        fail("email %s is %r, expected %r" % (field, outbox[0].get(field), value))

print("ok")
