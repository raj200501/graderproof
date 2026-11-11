import csv
import json
import os
import re
import sys

MONEY = re.compile(r"^-?\d+\.\d{2}$")


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


for path in ("by_category.csv", "summary.json"):
    if not os.path.isfile(path):
        fail("%s was not created" % path)

with open("by_category.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.reader(fh))
if not rows or rows[0] != ["category", "total"]:
    fail("by_category.csv must start with the header category,total")
body = rows[1:]
if not body:
    fail("by_category.csv has no categories")
names = [row[0] for row in body]
if names != sorted(names) or len(set(names)) != len(names):
    fail("categories must be unique and sorted: %r" % names)
for row in body:
    if len(row) != 2 or not MONEY.match(row[1]):
        fail("bad row in by_category.csv: %r" % (row,))

try:
    with open("summary.json", encoding="utf-8") as fh:
        summary = json.load(fh)
except ValueError as exc:
    fail("summary.json is not valid JSON: %s" % exc)
if not isinstance(summary, dict) or set(summary) != {"categories", "grand_total"}:
    fail("summary.json must have exactly the keys categories and grand_total")
if summary["categories"] != len(body):
    fail("summary says %r categories, by_category.csv has %d" % (summary["categories"], len(body)))
total = sum(float(row[1]) for row in body)
if not isinstance(summary["grand_total"], (int, float)) or abs(summary["grand_total"] - total) > 0.005:
    fail("grand_total %r does not match the category totals (%.2f)" % (summary["grand_total"], total))

print("ok")
