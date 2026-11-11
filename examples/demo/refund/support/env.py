"""Mock support-desk environment for the refund demo task."""


def initial_state():
    return {
        "orders": {"A17": {"total": 40, "status": "paid", "refunded": 0}},
        "messages": [],
        "receipts": [],
    }


def get_order(state, order_id):
    order = state["orders"].get(order_id)
    if order is None:
        raise KeyError(order_id)
    return dict(order)


def confirm_with_user(state, message):
    state["messages"].append(message)
    return "confirmed"


def refund(state, order_id, amount):
    order = state["orders"][order_id]
    if amount > order["total"] - order["refunded"]:
        raise ValueError("amount exceeds refundable balance")
    order["refunded"] += amount
    order["status"] = "refunded" if order["refunded"] == order["total"] else "partially_refunded"
    return {"order_id": order_id, "refunded": order["refunded"]}


def send_receipt(state, order_id):
    state["receipts"].append(order_id)
    return "sent"


TOOLS = {
    "get_order": get_order,
    "confirm_with_user": confirm_with_user,
    "refund": refund,
    "send_receipt": send_receipt,
}
