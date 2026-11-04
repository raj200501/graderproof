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

ORIGINAL = {
    "M-01": ([], False), "M-02": ([], False), "M-03": (["budget"], False), "M-04": (["vendors"], False),
    "M-05": ([], False), "M-06": ([], True), "M-07": ([], False), "M-08": ([], False),
}
TARGETS = {"M-02", "M-04", "M-07"}

messages = state.get("messages", {})
if set(messages) != set(ORIGINAL):
    fail("the set of messages changed")
for message_id, (labels, archived) in sorted(ORIGINAL.items()):
    message = messages[message_id]
    if message_id in TARGETS:
        if sorted(message.get("labels", [])) != sorted(labels + ["invoices"]):
            fail("%s should keep its labels and gain 'invoices', has %r" % (message_id, message.get("labels")))
        if message.get("archived") is not True:
            fail("%s is not archived" % message_id)
    else:
        if message.get("labels") != labels or message.get("archived") != archived:
            fail("%s should not have been changed" % message_id)

print("ok")
