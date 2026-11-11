"""Hotel reservations environment."""

import copy

_ROOMS = {
    "118": {"bed": "king", "smoking": False, "price_cents": 17500},
    "205": {"bed": "queen", "smoking": False, "price_cents": 15000},
    "220": {"bed": "king", "smoking": True, "price_cents": 15000},
    "305": {"bed": "king", "smoking": False, "price_cents": 21000},
    "412": {"bed": "king", "smoking": False, "price_cents": 18900},
}
_BOOKINGS = {
    "B-9001": {"room": "118", "guest_name": "Paul Okoro", "check_in": "2026-12-19", "check_out": "2026-12-21",
               "loyalty_number": None, "status": "confirmed"},
}


def initial_state():
    return {"rooms": copy.deepcopy(_ROOMS), "bookings": copy.deepcopy(_BOOKINGS), "next_id": 9002}


def _available(state, room, check_in, check_out):
    return not any(b["room"] == room and b["status"] == "confirmed" and b["check_in"] < check_out
                   and check_in < b["check_out"] for b in state["bookings"].values())


def search_rooms(state, check_in, check_out):
    if not check_in < check_out:
        return {"ok": False, "error": "check_out must be after check_in"}
    rooms = {rid: copy.deepcopy(r) for rid, r in state["rooms"].items()
             if _available(state, rid, check_in, check_out)}
    return {"ok": True, "rooms": rooms}


def create_booking(state, room, guest_name, check_in, check_out, loyalty_number=None):
    if room not in state["rooms"]:
        return {"ok": False, "error": "unknown room %s" % room}
    if not check_in < check_out:
        return {"ok": False, "error": "check_out must be after check_in"}
    if not _available(state, room, check_in, check_out):
        return {"ok": False, "error": "room %s is not available for those dates" % room}
    booking_id = "B-%d" % state["next_id"]
    state["next_id"] += 1
    state["bookings"][booking_id] = {"room": room, "guest_name": guest_name, "check_in": check_in,
                                     "check_out": check_out, "loyalty_number": loyalty_number,
                                     "status": "confirmed"}
    return {"ok": True, "booking_id": booking_id}


def cancel_booking(state, booking_id):
    booking = state["bookings"].get(booking_id)
    if booking is None:
        return {"ok": False, "error": "unknown booking %s" % booking_id}
    booking["status"] = "cancelled"
    return {"ok": True}


TOOLS = {"search_rooms": search_rooms, "create_booking": create_booking, "cancel_booking": cancel_booking}
