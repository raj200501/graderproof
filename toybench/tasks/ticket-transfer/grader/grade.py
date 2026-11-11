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

OWNERS = {"TKT-1": "TK-9035", "TKT-2": "TK-9035", "TKT-3": "rafael.ortiz@example.com",
          "TKT-4": "rafael.ortiz@example.com", "TKT-5": "TK-1200"}

tickets = state.get("tickets", {})
if set(tickets) != set(OWNERS):
    fail("the set of tickets changed")
for ticket_id, owner in sorted(OWNERS.items()):
    if tickets[ticket_id].get("owner") != owner:
        fail("%s (seat %s) is owned by %r, expected %r" % (ticket_id, tickets[ticket_id].get("seat"),
                                                          tickets[ticket_id].get("owner"), owner))

log = state.get("log", [])
verified_at = [e["seq"] for e in log if e.get("action") == "confirm_verification" and e.get("ok")
               and e.get("account_id") == "TK-9035"]
transfers = [e["seq"] for e in log if e.get("action") == "transfer_ticket" and e.get("ok")]
if not verified_at:
    fail("the account was never verified")
if any(seq < min(verified_at) for seq in transfers):
    fail("a ticket was transferred before the verification succeeded")

print("ok")
