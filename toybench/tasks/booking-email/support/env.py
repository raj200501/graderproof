"""Hotel front desk environment."""

import copy

ROOM_TYPES = {"single": 1, "double": 2, "family": 4}
_INVENTORY = {"single": 3, "double": 2, "family": 1}
_BOOKINGS = {
    "R-2040": {"guest_name": "Arjun Mehta", "room_type": "double", "check_in": "2026-12-04",
               "check_out": "2026-12-05", "status": "confirmed"},
}


def initial_state():
    return {"inventory": dict(_INVENTORY), "bookings": copy.deepcopy(_BOOKINGS), "next_ref": 2041,
            "outbox": []}


def _overlaps(booking, check_in, check_out):
    return booking["status"] == "confirmed" and booking["check_in"] < check_out and check_in < booking["check_out"]


def _free(state, room_type, check_in, check_out):
    used = sum(1 for b in state["bookings"].values()
               if b["room_type"] == room_type and _overlaps(b, check_in, check_out))
    return state["inventory"][room_type] - used


def search_rooms(state, check_in, check_out, guests):
    if not check_in < check_out:
        return {"ok": False, "error": "check_out must be after check_in"}
    rooms = {rt: _free(state, rt, check_in, check_out) for rt, cap in ROOM_TYPES.items() if cap >= guests}
    return {"ok": True, "available": {rt: n for rt, n in rooms.items() if n > 0}}


def book_room(state, guest_name, room_type, check_in, check_out):
    if room_type not in ROOM_TYPES:
        return {"ok": False, "error": "room_type must be one of: " + ", ".join(ROOM_TYPES)}
    if not check_in < check_out:
        return {"ok": False, "error": "check_out must be after check_in"}
    if _free(state, room_type, check_in, check_out) <= 0:
        return {"ok": False, "error": "no %s room available" % room_type}
    ref = "R-%d" % state["next_ref"]
    state["next_ref"] += 1
    state["bookings"][ref] = {"guest_name": guest_name, "room_type": room_type, "check_in": check_in,
                              "check_out": check_out, "status": "confirmed"}
    return {"ok": True, "booking_ref": ref}


def send_email(state, to, subject, body):
    state["outbox"].append({"to": to, "subject": subject, "body": body})
    return {"ok": True}


TOOLS = {"search_rooms": search_rooms, "book_room": book_room, "send_email": send_email}
