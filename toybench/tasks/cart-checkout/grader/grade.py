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

ITEMS = [{"sku": "TEA-01", "name": "Sencha 100 g", "qty": 2, "price_cents": 899},
         {"sku": "KET-07", "name": "Gooseneck kettle", "qty": 1, "price_cents": 5900}]

orders = state.get("orders", [])
if len(orders) != 1:
    fail("expected exactly one order, found %d" % len(orders))
order = orders[0]
items = sorted(order.get("items", []), key=lambda item: item.get("sku", ""))
if items != sorted(ITEMS, key=lambda item: item["sku"]):
    fail("order items are %r" % (order.get("items"),))
if order.get("coupon") != "WINTER10" or order.get("discount_cents") != 769:
    fail("coupon WINTER10 was not applied (coupon %r, discount %r)" % (order.get("coupon"), order.get("discount_cents")))
if order.get("total_cents") != 6929:
    fail("order total is %r cents, expected 6929" % (order.get("total_cents"),))
if order.get("ship_to") != "Unit 4, 22 Wharf Road, Leeds LS1 4DT":
    fail("order ships to %r, expected the office address" % (order.get("ship_to"),))

print("ok")
