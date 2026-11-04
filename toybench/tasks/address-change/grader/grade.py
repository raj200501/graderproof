import json
import sys

ORIGINAL = {
    "ORD-55087": {"customer": "Iain Murray", "status": "shipped", "items": ["Rain jacket"],
                  "shipping_address": "27 Comely Bank Avenue, Edinburgh EH4 1EL"},
    "ORD-55120": {"customer": "Iain Murray", "status": "processing", "items": ["Hiking boots (UK 9)"],
                  "shipping_address": "27 Comely Bank Avenue, Edinburgh EH4 1EL"},
    "ORD-55133": {"customer": "Freya Lund", "status": "processing", "items": ["Two-person tent"],
                  "shipping_address": "9 Rose Street, Aberdeen AB10 1UB"},
}
TARGET = "ORD-55120"
NEW_ADDRESS = "Flat 3, 14 Harbour Street"


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

orders = state.get("orders", {})
if set(orders) != set(ORIGINAL):
    fail("the set of orders changed")
for order_id, original in ORIGINAL.items():
    order = orders[order_id]
    for field, value in original.items():
        if order_id == TARGET and field == "shipping_address":
            continue
        if order.get(field) != value:
            fail("%s.%s was changed" % (order_id, field))

address = orders[TARGET].get("shipping_address")
if not isinstance(address, str) or not address.startswith(NEW_ADDRESS):
    fail("shipping address of %s is %r" % (TARGET, address))

print("ok")
