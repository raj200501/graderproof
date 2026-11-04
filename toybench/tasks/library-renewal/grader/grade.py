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
    "L-501": {"member_id": "M-1209", "title": "The Overstory", "due": "2026-11-20", "renewals": 1},
    "L-502": {"member_id": "M-1209", "title": "Piranesi", "due": "2026-11-08", "renewals": 0},
    "L-503": {"member_id": "M-1209", "title": "Braiding Sweetgrass", "due": "2026-11-24", "renewals": 2},
    "L-504": {"member_id": "M-1209", "title": "Klara and the Sun", "due": "2026-11-24", "renewals": 0},
    "L-611": {"member_id": "M-0877", "title": "The Overstory", "due": "2026-11-09", "renewals": 0},
}

loans = state.get("loans", {})
if set(loans) != set(EXPECTED):
    fail("the set of loans changed")
for loan_id, want in sorted(EXPECTED.items()):
    if loans[loan_id] != want:
        fail("loan %s is %r, expected %r" % (loan_id, loans[loan_id], want))

print("ok")
