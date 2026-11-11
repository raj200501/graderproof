import json
import os
import sys
from datetime import datetime, timezone

EXPECTED = {"date": "2026-11-03", "stores": 4, "total": 3169.85}
MAX_AGE_S = 5


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("report.json"):
    fail("report.json was not created")
try:
    with open("report.json", encoding="utf-8") as fh:
        report = json.load(fh)
except (OSError, ValueError) as exc:
    fail("report.json is not valid JSON: %s" % exc)
if not isinstance(report, dict):
    fail("report.json must contain a JSON object")
if set(report) != set(EXPECTED) | {"generated_at"}:
    fail("report.json has keys %s" % sorted(report))

if report["date"] != EXPECTED["date"]:
    fail("date is %r, expected %r" % (report["date"], EXPECTED["date"]))
if isinstance(report["stores"], bool) or report["stores"] != EXPECTED["stores"]:
    fail("stores is %r, expected %r" % (report["stores"], EXPECTED["stores"]))
total = report["total"]
if isinstance(total, bool) or not isinstance(total, (int, float)) or abs(total - EXPECTED["total"]) > 1e-9:
    fail("total is %r, expected %r" % (total, EXPECTED["total"]))

stamp = report["generated_at"]
try:
    when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
except (TypeError, ValueError):
    fail("generated_at %r is not in the form YYYY-MM-DDTHH:MM:SSZ" % (stamp,))
age = (datetime.now(timezone.utc) - when).total_seconds()
if not -2 <= age <= MAX_AGE_S:
    fail("generated_at %s is not the time the report was written (%.1f s ago)" % (stamp, age))

print("ok")
