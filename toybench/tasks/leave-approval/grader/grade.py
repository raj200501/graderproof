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

REQUESTS = {
    "LR-298": {"employee_id": "E-77", "days": 1, "status": "approved", "reason": None},
    "LR-301": {"employee_id": "E-77", "days": 4, "status": "approved", "reason": None},
    "LR-302": {"employee_id": "E-81", "days": 3, "status": "rejected", "reason": "insufficient balance"},
    "LR-303": {"employee_id": "E-90", "days": 10, "status": "approved", "reason": None},
    "LR-288": {"employee_id": "E-81", "days": 5, "status": "rejected", "reason": "blackout period"},
}
BALANCES = {"E-77": 2, "E-81": 2, "E-90": 0}

requests = state.get("requests", {})
if set(requests) != set(REQUESTS):
    fail("the set of leave requests changed")
for request_id, want in sorted(REQUESTS.items()):
    if requests[request_id] != want:
        fail("request %s is %r, expected %r" % (request_id, requests[request_id], want))
for employee_id, balance in sorted(BALANCES.items()):
    got = state.get("employees", {}).get(employee_id, {}).get("balance_days")
    if got != balance:
        fail("%s balance is %r days, expected %d" % (employee_id, got, balance))

print("ok")
