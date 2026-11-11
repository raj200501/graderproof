"""Tour operator booking environment."""

import copy

_BOOKINGS = {
    "BK-4470": {"customer": "Lin Zhao", "tour": "Porto old town walk", "date": "2026-12-05", "status": "confirmed"},
    "BK-4471": {"customer": "Lin Zhao", "tour": "Douro valley day trip", "date": "2026-12-12", "status": "confirmed"},
    "BK-4502": {"customer": "Tiago Costa", "tour": "Douro valley day trip", "date": "2026-12-12",
                "status": "confirmed"},
}


def initial_state():
    return {"bookings": copy.deepcopy(_BOOKINGS)}


def find_bookings(state, customer_name):
    return {"ok": True, "bookings": {bid: copy.deepcopy(b) for bid, b in sorted(state["bookings"].items())
                                     if b["customer"] == customer_name}}


def cancel_booking(state, booking_id):
    booking = state["bookings"].get(booking_id)
    if booking is None:
        return {"ok": False, "error": "unknown booking %s" % booking_id}
    booking["status"] = "cancelled"
    return {"ok": True}


TOOLS = {"find_bookings": find_bookings, "cancel_booking": cancel_booking}
