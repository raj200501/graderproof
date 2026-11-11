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

EXPECTED = {
    "CL-TUE-YOGA": {"title": "Yoga flow", "day": "Tuesday", "time": "18:00", "capacity": 3,
                    "roster": ["G-111", "G-305"], "waitlist": []},
    "CL-THU-YOGA": {"title": "Yoga flow", "day": "Thursday", "time": "18:00", "capacity": 2,
                    "roster": ["G-120", "G-311"], "waitlist": ["G-150", "G-208"]},
    "CL-SAT-YOGA": {"title": "Slow yoga", "day": "Saturday", "time": "10:00", "capacity": 4,
                    "roster": ["G-111"], "waitlist": []},
}

classes = state.get("classes", {})
if set(classes) != set(EXPECTED):
    fail("the set of classes changed")
for class_id, want in sorted(EXPECTED.items()):
    if classes[class_id] != want:
        fail("%s is %r, expected %r" % (class_id, classes[class_id], want))

print("ok")
