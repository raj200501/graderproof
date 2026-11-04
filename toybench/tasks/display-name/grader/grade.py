import json
import sys

UNCHANGED = {
    "U-7781": {"title": "Data Analyst", "phone": "+1 312 555 0148", "department": "Analytics"},
    "U-7790": {"display_name": "Luis Ferreira", "pronouns": "he/him", "title": "Product Designer",
               "phone": "+1 312 555 0191", "department": "Design"},
}
WANTED = {"display_name": "Maya R. Okafor", "pronouns": "she/her"}


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

users = state.get("users", {})
if set(users) != set(UNCHANGED):
    fail("the set of users changed")
for user_id, fields in UNCHANGED.items():
    for field, value in fields.items():
        if users[user_id].get(field) != value:
            fail("%s.%s was changed" % (user_id, field))

profile = users["U-7781"]
for field, value in WANTED.items():
    got = profile.get(field)
    if not isinstance(got, str) or got.casefold() != value.casefold():
        fail("U-7781.%s is %r, expected %r" % (field, got, value))

print("ok")
