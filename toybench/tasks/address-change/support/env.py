"""Online shop order environment."""

import copy

_ORDERS = {
    "ORD-55087": {"customer": "Iain Murray", "status": "shipped", "items": ["Rain jacket"],
                  "shipping_address": "27 Comely Bank Avenue, Edinburgh EH4 1EL"},
    "ORD-55120": {"customer": "Iain Murray", "status": "processing", "items": ["Hiking boots (UK 9)"],
                  "shipping_address": "27 Comely Bank Avenue, Edinburgh EH4 1EL"},
    "ORD-55133": {"customer": "Freya Lund", "status": "processing", "items": ["Two-person tent"],
                  "shipping_address": "9 Rose Street, Aberdeen AB10 1UB"},
}


def initial_state():
    return {"orders": copy.deepcopy(_ORDERS)}


def get_order(state, order_id):
    order = state["orders"].get(order_id)
    if order is None:
        return {"ok": False, "error": "unknown order %s" % order_id}
    return {"ok": True, "order": copy.deepcopy(order)}


def update_shipping_address(state, order_id, address):
    order = state["orders"].get(order_id)
    if order is None:
        return {"ok": False, "error": "unknown order %s" % order_id}
    if order["status"] != "processing":
        return {"ok": False, "error": "order %s has already shipped" % order_id}
    if not isinstance(address, str) or not address.strip():
        return {"ok": False, "error": "address must be a non-empty string"}
    order["shipping_address"] = address
    return {"ok": True}


TOOLS = {"get_order": get_order, "update_shipping_address": update_shipping_address}
