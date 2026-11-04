import json
import sys

EXISTING = {
    "T-0998": {"user_id": "U-204", "title": "Cannot print to floor 3 printer", "category": "hardware",
               "priority": "low", "team": "desktop", "status": "closed", "comments": []},
    "T-1000": {"user_id": "U-311", "title": "CRM export times out", "category": "software",
               "priority": "medium", "team": "apps", "status": "open", "comments": []},
}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

tickets = state.get("tickets", {})
for ticket_id, original in EXISTING.items():
    if tickets.get(ticket_id) != original:
        fail("existing ticket %s was modified" % ticket_id)

new = {tid: t for tid, t in tickets.items() if tid not in EXISTING}
if len(new) != 1:
    fail("expected exactly one new ticket, found %d" % len(new))
ticket_id, ticket = next(iter(new.items()))
if ticket.get("user_id") != "U-204":
    fail("ticket %s was not opened for Ana Lima (U-204)" % ticket_id)
for field in ("title", "category", "priority", "team"):
    if not ticket.get(field):
        fail("ticket %s has no %s" % (ticket_id, field))
if ticket.get("status") != "open":
    fail("ticket %s should be open, is %r" % (ticket_id, ticket.get("status")))

print("ok")
