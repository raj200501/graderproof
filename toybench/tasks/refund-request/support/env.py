"""E-commerce customer support environment."""

import copy

_CUSTOMERS = {
    "C-8812": {"name": "Tomás Rivera", "card_last4": "4821"},
    "C-8840": {"name": "Helen Achebe", "card_last4": "1177"},
}
_ORDERS = {
    "ORD-90417": {"customer_id": "C-8812", "status": "delivered", "refunded_cents": 0,
                  "items": [{"sku": "BLD-200", "name": "Countertop blender", "price_cents": 6499},
                            {"sku": "MUG-12", "name": "Travel mug", "price_cents": 1299}]},
    "ORD-90388": {"customer_id": "C-8840", "status": "delivered", "refunded_cents": 0,
                  "items": [{"sku": "KTL-07", "name": "Electric kettle", "price_cents": 3450}]},
}


def initial_state():
    return {"customers": copy.deepcopy(_CUSTOMERS), "orders": copy.deepcopy(_ORDERS),
            "refunds": [], "verified": []}


def verify_identity(state, customer_id, last4):
    customer = state["customers"].get(customer_id)
    if customer is None or customer["card_last4"] != str(last4):
        return {"ok": False, "verified": False}
    if customer_id not in state["verified"]:
        state["verified"].append(customer_id)
    return {"ok": True, "verified": True}


def get_order(state, order_id):
    order = state["orders"].get(order_id)
    if order is None:
        return {"ok": False, "error": "unknown order %s" % order_id}
    return {"ok": True, "order": copy.deepcopy(order)}


def issue_refund(state, order_id, amount_cents, reason):
    order = state["orders"].get(order_id)
    if order is None:
        return {"ok": False, "error": "unknown order %s" % order_id}
    total = sum(item["price_cents"] for item in order["items"])
    if not isinstance(amount_cents, int) or amount_cents <= 0 or order["refunded_cents"] + amount_cents > total:
        return {"ok": False, "error": "invalid refund amount"}
    order["refunded_cents"] += amount_cents
    order["status"] = "refunded" if order["refunded_cents"] == total else "partially_refunded"
    state["refunds"].append({"order_id": order_id, "amount_cents": amount_cents, "reason": reason})
    return {"ok": True, "refund_id": "RF-%d" % len(state["refunds"])}


TOOLS = {"verify_identity": verify_identity, "get_order": get_order, "issue_refund": issue_refund}
