import json
import os
import sys

EXPECTED = {
    "APP_NAME": "booking-api",
    "APP_PORT": "9090",
    "DATABASE_URL": "postgres://booking@db.internal:5432/booking",
    "FEATURE_FLAGS": "search,waitlist",
    "LOG_LEVEL": "info",
    "EMPTY_VALUE": "",
    "GREETING": 'Welcome to "Harbour" Hotels',
    "CACHE_TTL": "300 # seconds",
}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("config.json"):
    fail("config.json was not created")
try:
    with open("config.json", encoding="utf-8") as fh:
        config = json.load(fh)
except (OSError, ValueError) as exc:
    fail("config.json is not valid JSON: %s" % exc)
if not isinstance(config, dict):
    fail("config.json must contain a JSON object")

if set(config) != set(EXPECTED):
    fail("keys are %s, expected %s" % (sorted(config), sorted(EXPECTED)))
for key, value in EXPECTED.items():
    if config[key] != value:
        fail("%s is %r, expected %r" % (key, config[key], value))

print("ok")
