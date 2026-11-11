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

EXISTING = {"room": "118", "guest_name": "Paul Okoro", "check_in": "2026-12-19", "check_out": "2026-12-21",
            "loyalty_number": None, "status": "confirmed"}
WANTED = {"room": "412", "guest_name": "Elif Demir", "check_in": "2026-12-18", "check_out": "2026-12-20",
          "loyalty_number": "LY-55821", "status": "confirmed"}

bookings = state.get("bookings", {})
if bookings.get("B-9001") != EXISTING:
    fail("existing booking B-9001 was changed")
new = {bid: b for bid, b in bookings.items() if bid != "B-9001"}
if len(new) != 1:
    fail("expected exactly one new booking, found %d" % len(new))
booking_id, booking = next(iter(new.items()))
if booking != WANTED:
    fail("booking %s is %r, expected %r" % (booking_id, booking, WANTED))

print("ok")
