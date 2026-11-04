"""Event ticketing environment."""

import copy

_TICKETS = {
    "TKT-1": {"event": "Jazz at the Pier", "seat": "A10", "owner": "TK-9035"},
    "TKT-2": {"event": "Jazz at the Pier", "seat": "A11", "owner": "TK-9035"},
    "TKT-3": {"event": "Jazz at the Pier", "seat": "A12", "owner": "TK-9035"},
    "TKT-4": {"event": "Jazz at the Pier", "seat": "A13", "owner": "TK-9035"},
    "TKT-5": {"event": "Jazz at the Pier", "seat": "A14", "owner": "TK-1200"},
}
_CODE = "481516"


def initial_state():
    return {"tickets": copy.deepcopy(_TICKETS), "codes_sent": [], "verified": [], "log": []}


def _log(state, action, ok, **fields):
    state["log"].append(dict(seq=len(state["log"]) + 1, action=action, ok=ok, **fields))


def list_tickets(state, account_id):
    return {"ok": True, "tickets": {tid: copy.deepcopy(t) for tid, t in sorted(state["tickets"].items())
                                    if t["owner"] == account_id}}


def send_verification_code(state, account_id):
    state["codes_sent"].append(account_id)
    _log(state, "send_verification_code", True, account_id=account_id)
    return {"ok": True, "message": "code sent by SMS"}


def confirm_verification(state, account_id, code):
    ok = account_id in state["codes_sent"] and str(code) == _CODE
    if ok and account_id not in state["verified"]:
        state["verified"].append(account_id)
    _log(state, "confirm_verification", ok, account_id=account_id)
    return {"ok": ok, "verified": ok}


def transfer_ticket(state, ticket_id, recipient_email):
    ticket = state["tickets"].get(ticket_id)
    if ticket is None or "@" not in str(recipient_email):
        _log(state, "transfer_ticket", False, ticket_id=ticket_id)
        return {"ok": False, "error": "unknown ticket or invalid email"}
    previous = ticket["owner"]
    ticket["owner"] = recipient_email
    _log(state, "transfer_ticket", True, ticket_id=ticket_id, from_owner=previous)
    return {"ok": True}


TOOLS = {"list_tickets": list_tickets, "send_verification_code": send_verification_code,
         "confirm_verification": confirm_verification, "transfer_ticket": transfer_ticket}
