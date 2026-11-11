"""Public library circulation environment."""

import copy
from datetime import date, timedelta

_LOANS = {
    "L-501": {"member_id": "M-1209", "title": "The Overstory", "due": "2026-11-06", "renewals": 0},
    "L-502": {"member_id": "M-1209", "title": "Piranesi", "due": "2026-11-08", "renewals": 0},
    "L-503": {"member_id": "M-1209", "title": "Braiding Sweetgrass", "due": "2026-11-10", "renewals": 1},
    "L-504": {"member_id": "M-1209", "title": "Klara and the Sun", "due": "2026-11-24", "renewals": 0},
    "L-611": {"member_id": "M-0877", "title": "The Overstory", "due": "2026-11-09", "renewals": 0},
}
_HOLDS = {"Piranesi": ["M-0877"], "Klara and the Sun": ["M-1301"]}


def initial_state():
    return {"loans": copy.deepcopy(_LOANS), "holds": copy.deepcopy(_HOLDS)}


def list_loans(state, member_id):
    loans = {}
    for loan_id, loan in sorted(state["loans"].items()):
        if loan["member_id"] == member_id:
            others = [m for m in state["holds"].get(loan["title"], []) if m != member_id]
            loans[loan_id] = dict(loan, holds_by_others=len(others))
    return {"ok": True, "loans": loans}


def renew_loan(state, loan_id):
    loan = state["loans"].get(loan_id)
    if loan is None:
        return {"ok": False, "error": "unknown loan %s" % loan_id}
    loan["due"] = (date.fromisoformat(loan["due"]) + timedelta(days=14)).isoformat()
    loan["renewals"] += 1
    return {"ok": True, "due": loan["due"]}


TOOLS = {"list_loans": list_loans, "renew_loan": renew_loan}
