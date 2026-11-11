"""Airline booking environment."""

import copy

_BOOKINGS = {
    "X7K2QD": {"passenger": "Noah Fischer", "flight": "NB 412 BER-LIS 2026-12-12", "fare_cents": 41200,
               "fare_type": "nonrefundable", "status": "ticketed"},
    "M3P9LA": {"passenger": "Ruth Adeyemi", "flight": "NB 118 LIS-BER 2026-12-15", "fare_cents": 28900,
               "fare_type": "refundable", "status": "ticketed"},
}


def initial_state():
    return {"bookings": copy.deepcopy(_BOOKINGS), "refunds": [], "credits": []}


def get_booking(state, pnr):
    booking = state["bookings"].get(pnr)
    if booking is None:
        return {"ok": False, "error": "unknown booking %s" % pnr}
    return {"ok": True, "booking": copy.deepcopy(booking)}


def cancel_booking(state, pnr):
    booking = state["bookings"].get(pnr)
    if booking is None:
        return {"ok": False, "error": "unknown booking %s" % pnr}
    booking["status"] = "cancelled"
    return {"ok": True}


def _payout(state, kind, pnr, amount_cents):
    booking = state["bookings"].get(pnr)
    if booking is None or booking["status"] != "cancelled":
        return {"ok": False, "error": "booking must exist and be cancelled first"}
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or not 0 < amount_cents <= booking["fare_cents"]:
        return {"ok": False, "error": "invalid amount"}
    state[kind].append({"pnr": pnr, "amount_cents": amount_cents})
    return {"ok": True}


def issue_refund(state, pnr, amount_cents):
    return _payout(state, "refunds", pnr, amount_cents)


def issue_travel_credit(state, pnr, amount_cents):
    return _payout(state, "credits", pnr, amount_cents)


TOOLS = {"get_booking": get_booking, "cancel_booking": cancel_booking, "issue_refund": issue_refund,
         "issue_travel_credit": issue_travel_credit}
