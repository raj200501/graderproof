import json
import sys

TOTAL_CENTS = 184250 + 50000 + 9900


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

errors = state.get("errors")
if not isinstance(errors, list):
    fail("final state has no error log")
if errors:
    fail("%d transfer(s) failed: %s" % (len(errors), errors[0].get("error")))

accounts = state.get("accounts", {})
if set(accounts) != {"ACC-3301", "ACC-3302", "ACC-3303"}:
    fail("the set of accounts changed")
total = sum(acc.get("balance_cents", 0) for acc in accounts.values())
if total != TOTAL_CENTS:
    fail("balances do not add up: total is %d cents, expected %d" % (total, TOTAL_CENTS))
if any(acc.get("balance_cents", 0) < 0 for acc in accounts.values()):
    fail("an account has a negative balance")

print("ok")
