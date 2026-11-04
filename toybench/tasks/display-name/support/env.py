"""Staff directory environment."""

import copy

FIELDS = ("display_name", "pronouns", "title", "phone")
_USERS = {
    "U-7781": {"display_name": "MAYA OKAFOR", "pronouns": "", "title": "Data Analyst",
               "phone": "+1 312 555 0148", "department": "Analytics"},
    "U-7790": {"display_name": "Luis Ferreira", "pronouns": "he/him", "title": "Product Designer",
               "phone": "+1 312 555 0191", "department": "Design"},
}


def initial_state():
    return {"users": copy.deepcopy(_USERS)}


def get_profile(state, user_id):
    user = state["users"].get(user_id)
    if user is None:
        return {"ok": False, "error": "unknown user %s" % user_id}
    return {"ok": True, "profile": copy.deepcopy(user)}


def update_profile(state, user_id, field, value):
    user = state["users"].get(user_id)
    if user is None:
        return {"ok": False, "error": "unknown user %s" % user_id}
    if field not in FIELDS:
        return {"ok": False, "error": "field must be one of: " + ", ".join(FIELDS)}
    if not isinstance(value, str):
        return {"ok": False, "error": "value must be a string"}
    user[field] = value
    return {"ok": True}


TOOLS = {"get_profile": get_profile, "update_profile": update_profile}
