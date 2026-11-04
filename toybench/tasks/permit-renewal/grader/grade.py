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

log = state.get("call_log")
if not isinstance(log, list) or not log:
    fail("no permit transactions were recorded")
for i, entry in enumerate(log):
    if entry.get("status") != "ok":
        fail("call %d (%s) failed: %s" % (i + 1, entry.get("tool"), entry.get("detail")))

print("ok")
