"""Helpdesk ticketing environment."""

import copy

CATEGORIES = ("hardware", "software", "network", "access")
PRIORITIES = ("low", "medium", "high", "urgent")
TEAMS = ("desktop", "netops", "identity", "apps")

_USERS = {
    "U-204": {"name": "Ana Lima", "email": "ana.lima@example.com", "department": "Finance"},
    "U-311": {"name": "Ben Ochoa", "email": "ben.ochoa@example.com", "department": "Sales"},
    "U-412": {"name": "Ana Lindqvist", "email": "ana.lindqvist@example.com", "department": "Legal"},
}
_TICKETS = {
    "T-0998": {"user_id": "U-204", "title": "Cannot print to floor 3 printer", "category": "hardware",
               "priority": "low", "team": "desktop", "status": "closed", "comments": []},
    "T-1000": {"user_id": "U-311", "title": "CRM export times out", "category": "software",
               "priority": "medium", "team": "apps", "status": "open", "comments": []},
}


def initial_state():
    return {"users": copy.deepcopy(_USERS), "tickets": copy.deepcopy(_TICKETS), "next_ticket": 1001}


def _err(msg):
    return {"ok": False, "error": msg}


def find_user(state, email):
    for user_id, user in sorted(state["users"].items()):
        if user["email"].lower() == str(email).strip().lower():
            return {"ok": True, "user_id": user_id, "name": user["name"], "department": user["department"]}
    return _err("no user with email %s" % email)


def create_ticket(state, user_id, title, category, priority):
    if user_id not in state["users"]:
        return _err("unknown user %s" % user_id)
    if category not in CATEGORIES:
        return _err("category must be one of: " + ", ".join(CATEGORIES))
    if priority not in PRIORITIES:
        return _err("priority must be one of: " + ", ".join(PRIORITIES))
    if not str(title).strip():
        return _err("title is required")
    ticket_id = "T-%d" % state["next_ticket"]
    state["next_ticket"] += 1
    state["tickets"][ticket_id] = {"user_id": user_id, "title": title, "category": category,
                                   "priority": priority, "team": None, "status": "open", "comments": []}
    return {"ok": True, "ticket_id": ticket_id}


def assign_ticket(state, ticket_id, team):
    ticket = state["tickets"].get(ticket_id)
    if ticket is None:
        return _err("unknown ticket %s" % ticket_id)
    if team not in TEAMS:
        return _err("team must be one of: " + ", ".join(TEAMS))
    ticket["team"] = team
    return {"ok": True}


def add_comment(state, ticket_id, text):
    ticket = state["tickets"].get(ticket_id)
    if ticket is None:
        return _err("unknown ticket %s" % ticket_id)
    ticket["comments"].append(str(text))
    return {"ok": True}


def get_ticket(state, ticket_id):
    ticket = state["tickets"].get(ticket_id)
    if ticket is None:
        return _err("unknown ticket %s" % ticket_id)
    return {"ok": True, "ticket": copy.deepcopy(ticket)}


TOOLS = {
    "find_user": find_user,
    "create_ticket": create_ticket,
    "assign_ticket": assign_ticket,
    "add_comment": add_comment,
    "get_ticket": get_ticket,
}
