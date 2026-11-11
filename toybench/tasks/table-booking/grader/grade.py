import json
import sys

EXISTING = {
    "R-501": {"name": "Oliver Grant", "phone": "+44 20 7946 0102", "date": "2026-11-14", "time": "19:30",
              "party_size": 4, "table": "T3", "notes": "", "status": "booked"},
    "R-502": {"name": "Sofia Marin", "phone": "+44 20 7946 0877", "date": "2026-11-14", "time": "20:00",
              "party_size": 2, "table": "T1", "notes": "anniversary", "status": "booked"},
}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

reservations = state.get("reservations", {})
for rid, original in EXISTING.items():
    if reservations.get(rid) != original:
        fail("existing reservation %s was changed" % rid)

new = {rid: r for rid, r in reservations.items() if rid not in EXISTING}
if len(new) != 1:
    fail("expected exactly one new reservation, found %d" % len(new))
rid, booking = next(iter(new.items()))
if booking.get("name") != "Priya Raman":
    fail("reservation %s is not under the name Priya Raman" % rid)
if booking.get("status") != "booked":
    fail("reservation %s is not booked (status %r)" % (rid, booking.get("status")))
if not booking.get("table"):
    fail("reservation %s has no table" % rid)

print("ok")
