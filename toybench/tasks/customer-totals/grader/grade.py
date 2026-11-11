import os
import sys

EXPECTED_LINES = [
    "customer,total",
    '"Adventure Works, LLC",600.00',
    "Contoso Ltd,355.75",
    "Fabrikam Inc,2399.95",
    "Northwind Traders,1289.99",
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("totals.csv"):
    fail("totals.csv was not created")
with open("totals.csv", encoding="utf-8", newline="") as fh:
    lines = fh.read().split("\n")
if lines and lines[-1] == "":
    lines.pop()

for number, (got, want) in enumerate(zip(lines, EXPECTED_LINES), start=1):
    if got != want:
        fail("totals.csv line %d is %r, expected %r" % (number, got, want))
if len(lines) != len(EXPECTED_LINES):
    fail("totals.csv has %d lines, expected %d" % (len(lines), len(EXPECTED_LINES)))

print("ok")
