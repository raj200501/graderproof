import csv
import os
import sys


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def expected_usage(path):
    series = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            series.setdefault(row["meter"], []).append((row["date"], int(row["reading_kwh"])))
    return [[meter, str(max(s)[1] - min(s)[1])] for meter, s in sorted(series.items())]


for path in ("readings.csv", "usage.csv"):
    if not os.path.isfile(path):
        fail("%s is missing" % path)

try:
    expected = expected_usage("readings.csv")
except (KeyError, ValueError) as exc:
    fail("cannot read readings.csv: %s" % exc)
with open("usage.csv", newline="", encoding="utf-8") as fh:
    rows = [row for row in csv.reader(fh)]

if not rows or rows[0] != ["meter", "kwh"]:
    fail("usage.csv must start with the header meter,kwh")
if rows[1:] != expected:
    fail("usage.csv rows are %r, expected %r" % (rows[1:], expected))

print("ok")
