import json
import sys

TARGET = "RMA-7712"
MUTATING = ("mark_received", "refund_rma")


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/trajectory.json", encoding="utf-8") as fh:
        calls = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read the tool-call log: %s" % exc)

received = refunded = False
for call in calls:
    tool, args = call.get("tool"), call.get("args") or {}
    if tool in MUTATING and args.get("rma_id") != TARGET:
        fail("%s was called for %s; only %s may be changed" % (tool, args.get("rma_id"), TARGET))
    if tool == "mark_received" and args.get("condition") == "good":
        received = True
    if tool == "refund_rma":
        refunded = True

if not received:
    fail("%s was not marked as received in good condition" % TARGET)
if not refunded:
    fail("no refund was issued for %s" % TARGET)

print("ok")
