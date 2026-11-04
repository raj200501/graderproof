"""Returns (RMA) processing environment."""

import copy

_RMAS = {
    "RMA-7712": {"order_id": "ORD-61200", "item": "Trail running shoes", "amount_cents": 8900,
                 "status": "awaiting_return", "condition": None},
    "RMA-7720": {"order_id": "ORD-61377", "item": "Insulated bottle", "amount_cents": 2450,
                 "status": "awaiting_return", "condition": None},
}


def initial_state():
    return {"rmas": copy.deepcopy(_RMAS), "refunds": []}


def get_rma(state, rma_id):
    rma = state["rmas"].get(rma_id)
    if rma is None:
        return {"ok": False, "error": "unknown return %s" % rma_id}
    return {"ok": True, "rma": copy.deepcopy(rma)}


def mark_received(state, rma_id, condition):
    rma = state["rmas"].get(rma_id)
    if rma is None or condition not in ("good", "damaged") or rma["status"] != "awaiting_return":
        return {"ok": False, "error": "unknown return, invalid condition, or already received"}
    rma["status"], rma["condition"] = "received", condition
    return {"ok": True}


def refund_rma(state, rma_id):
    rma = state["rmas"].get(rma_id)
    if rma is None or rma["status"] != "received" or rma["condition"] != "good":
        return {"ok": False, "error": "return must be received in good condition before refunding"}
    rma["status"] = "refunded"
    state["refunds"].append({"rma_id": rma_id, "amount_cents": rma["amount_cents"]})
    return {"ok": True, "amount_cents": rma["amount_cents"]}


TOOLS = {"get_rma": get_rma, "mark_received": mark_received, "refund_rma": refund_rma}
