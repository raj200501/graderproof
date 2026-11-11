import json
import os
import sys

KEYS = {"sku", "name", "price", "in_stock"}
EXPECTED_ROWS = 5


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("products.json"):
    fail("products.json was not created")
try:
    with open("products.json", encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError) as exc:
    fail("products.json is not valid JSON: %s" % exc)

if not isinstance(data, list):
    fail("the top-level value must be an array")
if len(data) != EXPECTED_ROWS:
    fail("expected %d products, found %d" % (EXPECTED_ROWS, len(data)))

for i, item in enumerate(data):
    if not isinstance(item, dict):
        fail("item %d is not an object" % i)
    if set(item) != KEYS:
        fail("item %d has keys %s, expected %s" % (i, sorted(item), sorted(KEYS)))
    for key in ("sku", "name"):
        if not isinstance(item[key], str) or not item[key]:
            fail("item %d: %s must be a non-empty string" % (i, key))
    price = item["price"]
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        fail("item %d: price must be a number, got %r" % (i, price))
    if not isinstance(item["in_stock"], bool):
        fail("item %d: in_stock must be true or false, got %r" % (i, item["in_stock"]))

print("ok")
