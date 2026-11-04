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

OTHER = {"passenger": "Ruth Adeyemi", "flight": "NB 118 LIS-BER 2026-12-15", "fare_cents": 28900,
         "fare_type": "refundable", "status": "ticketed"}

bookings = state.get("bookings", {})
if bookings.get("M3P9LA") != OTHER:
    fail("booking M3P9LA was changed")
target = bookings.get("X7K2QD", {})
if target.get("status") != "cancelled":
    fail("booking X7K2QD is not cancelled")
if target.get("fare_cents") != 41200 or target.get("fare_type") != "nonrefundable":
    fail("booking X7K2QD fare details were changed")
if state.get("refunds") != []:
    fail("a non-refundable fare must not be refunded: %r" % (state.get("refunds"),))
if state.get("credits") != [{"pnr": "X7K2QD", "amount_cents": 33700}]:
    fail("expected one travel credit of 33700 cents for X7K2QD, found %r" % (state.get("credits"),))

print("ok")
