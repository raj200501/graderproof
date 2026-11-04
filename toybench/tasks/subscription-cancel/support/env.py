"""Meal-kit subscription environment."""

import copy

_SUBSCRIPTIONS = {
    "SUB-3381": {"customer": "Ola Nordmann", "plan": "weekly-2", "price_cents": 1500, "status": "active",
                 "paid_through": "2026-11-30"},
    "SUB-3390": {"customer": "Kari Nordmann", "plan": "weekly-4", "price_cents": 2600, "status": "active",
                 "paid_through": "2026-11-30"},
}


def initial_state():
    return {"subscriptions": copy.deepcopy(_SUBSCRIPTIONS), "refunds": []}


def get_subscription(state, sub_id):
    sub = state["subscriptions"].get(sub_id)
    if sub is None:
        return {"ok": False, "error": "unknown subscription %s" % sub_id}
    return {"ok": True, "subscription": copy.deepcopy(sub)}


def cancel_subscription(state, sub_id, when):
    sub = state["subscriptions"].get(sub_id)
    if sub is None or when not in ("immediately", "period_end"):
        return {"ok": False, "error": "unknown subscription or invalid 'when'"}
    sub["status"] = "cancelled" if when == "immediately" else "pending_cancellation"
    return {"ok": True, "status": sub["status"]}


def issue_refund(state, sub_id, amount_cents):
    sub = state["subscriptions"].get(sub_id)
    if sub is None or not isinstance(amount_cents, int) or not 0 < amount_cents <= sub["price_cents"]:
        return {"ok": False, "error": "unknown subscription or invalid amount"}
    state["refunds"].append({"sub_id": sub_id, "amount_cents": amount_cents})
    return {"ok": True}


TOOLS = {"get_subscription": get_subscription, "cancel_subscription": cancel_subscription,
         "issue_refund": issue_refund}
