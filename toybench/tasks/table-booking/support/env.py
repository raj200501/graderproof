"""Restaurant reservation environment."""

import copy

SLOTS = ("17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00")
_TABLES = {"T1": 2, "T2": 2, "T3": 4, "T4": 4, "T5": 6}
_RESERVATIONS = {
    "R-501": {"name": "Oliver Grant", "phone": "+44 20 7946 0102", "date": "2026-11-14", "time": "19:30",
              "party_size": 4, "table": "T3", "notes": "", "status": "booked"},
    "R-502": {"name": "Sofia Marin", "phone": "+44 20 7946 0877", "date": "2026-11-14", "time": "20:00",
              "party_size": 2, "table": "T1", "notes": "anniversary", "status": "booked"},
}


def initial_state():
    return {"tables": dict(_TABLES), "reservations": copy.deepcopy(_RESERVATIONS), "next_id": 503}


def _err(msg):
    return {"ok": False, "error": msg}


def _free_tables(state, date, time, party_size):
    taken = {r["table"] for r in state["reservations"].values()
             if r["status"] == "booked" and r["date"] == date and r["time"] == time}
    return sorted((size, tid) for tid, size in state["tables"].items() if tid not in taken and size >= party_size)


def _validate(time, party_size):
    if time not in SLOTS:
        return "time must be one of: " + ", ".join(SLOTS)
    if not isinstance(party_size, int) or isinstance(party_size, bool) or not 1 <= party_size <= 6:
        return "party_size must be an integer from 1 to 6"
    return None


def check_availability(state, date, time, party_size):
    problem = _validate(time, party_size)
    if problem:
        return _err(problem)
    return {"ok": True, "available": bool(_free_tables(state, date, time, party_size))}


def create_reservation(state, name, phone, date, time, party_size, notes=""):
    problem = _validate(time, party_size)
    if problem:
        return _err(problem)
    free = _free_tables(state, date, time, party_size)
    if not free:
        return _err("no table available for %d at %s %s" % (party_size, date, time))
    table = free[0][1]
    reservation_id = "R-%d" % state["next_id"]
    state["next_id"] += 1
    state["reservations"][reservation_id] = {"name": name, "phone": phone, "date": date, "time": time,
                                             "party_size": party_size, "table": table, "notes": notes,
                                             "status": "booked"}
    return {"ok": True, "reservation_id": reservation_id, "table": table}


def cancel_reservation(state, reservation_id):
    reservation = state["reservations"].get(reservation_id)
    if reservation is None:
        return _err("unknown reservation %s" % reservation_id)
    reservation["status"] = "cancelled"
    return {"ok": True}


def list_reservations(state, date):
    return {"ok": True, "reservations": {rid: copy.deepcopy(r) for rid, r in state["reservations"].items()
                                         if r["date"] == date}}


TOOLS = {
    "check_availability": check_availability,
    "create_reservation": create_reservation,
    "cancel_reservation": cancel_reservation,
    "list_reservations": list_reservations,
}
