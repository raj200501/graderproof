"""Shared calendar environment."""

import copy

_DIRECTORY = {
    "Lena Ortiz": "lena.ortiz@example.com",
    "Sam Cho": "sam.cho@example.com",
    "Priya Nair": "priya.nair@example.com",
    "Tom Becker": "tom.becker@example.com",
    "Finance team": "finance-team@example.com",
}
_EVENTS = {
    "EV-301": {"title": "Weekly sync", "date": "2026-11-12", "start": "10:00", "end": "10:30",
               "attendees": ["lena.ortiz@example.com", "tom.becker@example.com"]},
}


def initial_state():
    return {"directory": dict(_DIRECTORY), "events": copy.deepcopy(_EVENTS), "next_event": 302}


def find_person(state, name):
    matches = {n: e for n, e in state["directory"].items() if name.lower() in n.lower()}
    return {"ok": True, "matches": matches}


def list_events(state, date):
    return {"ok": True, "events": {eid: copy.deepcopy(ev) for eid, ev in state["events"].items()
                                   if ev["date"] == date}}


def _check_emails(emails):
    return isinstance(emails, list) and all(isinstance(e, str) and "@" in e for e in emails)


def create_event(state, title, date, start, end, attendees):
    if not _check_emails(attendees):
        return {"ok": False, "error": "attendees must be a list of email addresses"}
    if not (isinstance(start, str) and isinstance(end, str) and start < end):
        return {"ok": False, "error": "start must be before end"}
    event_id = "EV-%d" % state["next_event"]
    state["next_event"] += 1
    state["events"][event_id] = {"title": title, "date": date, "start": start, "end": end,
                                 "attendees": list(dict.fromkeys(attendees))}
    return {"ok": True, "event_id": event_id}


def add_attendees(state, event_id, emails):
    event = state["events"].get(event_id)
    if event is None:
        return {"ok": False, "error": "unknown event %s" % event_id}
    if not _check_emails(emails):
        return {"ok": False, "error": "emails must be a list of email addresses"}
    for email in emails:
        if email not in event["attendees"]:
            event["attendees"].append(email)
    return {"ok": True}


TOOLS = {"find_person": find_person, "list_events": list_events, "create_event": create_event,
         "add_attendees": add_attendees}
