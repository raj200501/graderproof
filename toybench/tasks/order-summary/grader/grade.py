import json
import os
import sys

EXPECTED = {"orders": 5, "units": 11, "revenue": 175.4, "top_product": "espresso beans 1kg"}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("summary.json"):
    fail("summary.json was not created")
try:
    with open("summary.json", encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError) as exc:
    fail("summary.json is not valid JSON: %s" % exc)

if not isinstance(data, dict):
    fail("summary.json must contain a JSON object")
if json.dumps(data) != json.dumps(EXPECTED):
    fail("summary is %s, expected %s" % (json.dumps(data), json.dumps(EXPECTED)))

print("ok")
