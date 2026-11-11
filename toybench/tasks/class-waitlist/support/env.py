"""Gym class booking environment."""

import copy

_CLASSES = {
    "CL-TUE-YOGA": {"title": "Yoga flow", "day": "Tuesday", "time": "18:00", "capacity": 3,
                    "roster": ["G-111", "G-208", "G-305"], "waitlist": []},
    "CL-THU-YOGA": {"title": "Yoga flow", "day": "Thursday", "time": "18:00", "capacity": 2,
                    "roster": ["G-120", "G-311"], "waitlist": ["G-150"]},
    "CL-SAT-YOGA": {"title": "Slow yoga", "day": "Saturday", "time": "10:00", "capacity": 4,
                    "roster": ["G-111"], "waitlist": []},
}


def initial_state():
    return {"classes": copy.deepcopy(_CLASSES)}


def list_classes(state):
    return {"ok": True, "classes": copy.deepcopy(state["classes"])}


def cancel_booking(state, member_id, class_id):
    cls = state["classes"].get(class_id)
    if cls is None or member_id not in cls["roster"]:
        return {"ok": False, "error": "member is not booked on this class"}
    cls["roster"].remove(member_id)
    return {"ok": True}


def book_class(state, member_id, class_id):
    cls = state["classes"].get(class_id)
    if cls is None:
        return {"ok": False, "error": "unknown class"}
    if member_id in cls["roster"]:
        return {"ok": False, "error": "already booked"}
    if len(cls["roster"]) >= cls["capacity"]:
        return {"ok": False, "error": "class is full"}
    cls["roster"].append(member_id)
    return {"ok": True}


def join_waitlist(state, member_id, class_id):
    cls = state["classes"].get(class_id)
    if cls is None or member_id in cls["roster"] or member_id in cls["waitlist"]:
        return {"ok": False, "error": "unknown class or member already booked or waiting"}
    cls["waitlist"].append(member_id)
    return {"ok": True, "position": len(cls["waitlist"])}


TOOLS = {"list_classes": list_classes, "cancel_booking": cancel_booking, "book_class": book_class,
         "join_waitlist": join_waitlist}
