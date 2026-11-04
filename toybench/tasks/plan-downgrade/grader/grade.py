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

OTHER = {"owner": "Lea Novak", "zip": "60657", "plan": "team", "next_billing": "2026-11-28",
         "pending_change": None, "notes": []}

accounts = state.get("accounts", {})
if accounts.get("AC-4471") != OTHER:
    fail("account AC-4471 was changed")
account = accounts.get("AC-4410", {})
if account.get("plan") != "pro":
    fail("the plan must not change before the end of the billing period (plan is %r)" % account.get("plan"))
if account.get("pending_change") != {"plan": "basic", "effective": "2026-11-21"}:
    fail("pending change is %r, expected basic at period end" % (account.get("pending_change"),))
if not any("downgrade" in str(note).lower() for note in account.get("notes", [])):
    fail("no account note mentions the downgrade")

audit = [e for e in state.get("audit", []) if e.get("account_id") == "AC-4410"]
changes = [e["seq"] for e in audit if e.get("action") == "schedule_plan_change" and e.get("ok")]
verified = [e["seq"] for e in audit if e.get("action") == "verify_account" and e.get("ok")]
if not changes:
    fail("no successful plan change was recorded")
if not verified or min(verified) > min(changes):
    fail("the account holder was not verified before the plan change")

print("ok")
