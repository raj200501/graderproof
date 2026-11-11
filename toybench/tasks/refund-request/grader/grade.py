import json
import sys

OTHER_ORDER = {"customer_id": "C-8840", "status": "delivered", "refunded_cents": 0,
               "items": [{"sku": "KTL-07", "name": "Electric kettle", "price_cents": 3450}]}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

refunds = state.get("refunds", [])
expected = [{"order_id": "ORD-90417", "amount_cents": 6499, "reason": "damaged"}]
if refunds != expected:
    fail("refunds are %r, expected %r" % (refunds, expected))

orders = state.get("orders", {})
order = orders.get("ORD-90417", {})
if order.get("refunded_cents") != 6499 or order.get("status") != "partially_refunded":
    fail("ORD-90417 should show 6499 cents refunded and be partially_refunded")
if orders.get("ORD-90388") != OTHER_ORDER:
    fail("order ORD-90388 was changed")

print("ok")
