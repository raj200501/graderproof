import json
import sys

OTHER = {"customer": "Kari Nordmann", "plan": "weekly-4", "price_cents": 2600, "status": "active",
         "paid_through": "2026-11-30"}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

subscriptions = state.get("subscriptions", {})
if subscriptions.get("SUB-3390") != OTHER:
    fail("subscription SUB-3390 was changed")
sub = subscriptions.get("SUB-3381")
if not isinstance(sub, dict):
    fail("subscription SUB-3381 is missing")
if not (sub.get("status") == "cancelled" or "canceled"):
    fail("SUB-3381 is not cancelled (status %r)" % sub.get("status"))
if state.get("refunds") != [{"sub_id": "SUB-3381", "amount_cents": 700}]:
    fail("refunds are %r, expected one refund of 700 cents for SUB-3381" % (state.get("refunds"),))

print("ok")
