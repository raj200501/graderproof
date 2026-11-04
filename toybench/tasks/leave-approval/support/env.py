"""HR leave management environment."""

import copy

_EMPLOYEES = {"E-77": {"name": "Sara Lindholm", "balance_days": 6},
              "E-81": {"name": "Diego Alvarez", "balance_days": 2},
              "E-90": {"name": "Mina Haddad", "balance_days": 10}}
_REQUESTS = {
    "LR-298": {"employee_id": "E-77", "days": 1, "status": "approved", "reason": None},
    "LR-301": {"employee_id": "E-77", "days": 4, "status": "pending", "reason": None},
    "LR-302": {"employee_id": "E-81", "days": 3, "status": "pending", "reason": None},
    "LR-303": {"employee_id": "E-90", "days": 10, "status": "pending", "reason": None},
    "LR-288": {"employee_id": "E-81", "days": 5, "status": "rejected", "reason": "blackout period"},
}


def initial_state():
    return {"employees": copy.deepcopy(_EMPLOYEES), "requests": copy.deepcopy(_REQUESTS)}


def list_requests(state, status):
    return {"ok": True, "requests": {rid: copy.deepcopy(r) for rid, r in sorted(state["requests"].items())
                                     if r["status"] == status}}


def get_balance(state, employee_id):
    employee = state["employees"].get(employee_id)
    if employee is None:
        return {"ok": False, "error": "unknown employee %s" % employee_id}
    return {"ok": True, "balance_days": employee["balance_days"]}


def approve_request(state, request_id):
    request = state["requests"].get(request_id)
    if request is None or request["status"] != "pending":
        return {"ok": False, "error": "request is not pending"}
    request["status"] = "approved"
    state["employees"][request["employee_id"]]["balance_days"] -= request["days"]
    return {"ok": True}


def reject_request(state, request_id, reason):
    request = state["requests"].get(request_id)
    if request is None or request["status"] != "pending":
        return {"ok": False, "error": "request is not pending"}
    request["status"] = "rejected"
    request["reason"] = reason
    return {"ok": True}


TOOLS = {"list_requests": list_requests, "get_balance": get_balance, "approve_request": approve_request,
         "reject_request": reject_request}
