"""Online tea shop checkout environment."""

import copy

COUPONS = {"WINTER10": {"percent": 10, "min_subtotal_cents": 2000}, "WELCOME5": {"percent": 5, "min_subtotal_cents": 0}}
_CUSTOMERS = {"CU-310": {"addresses": {"home": "8 Birch Lane, Leeds LS6 2AB", "office": "Unit 4, 22 Wharf Road, Leeds LS1 4DT"},
                         "cart": [{"sku": "TEA-01", "name": "Sencha 100 g", "qty": 2, "price_cents": 899},
                                  {"sku": "MUG-02", "name": "Stoneware mug", "qty": 1, "price_cents": 1450},
                                  {"sku": "KET-07", "name": "Gooseneck kettle", "qty": 1, "price_cents": 5900}],
                         "coupon": None}}


def initial_state():
    return {"customers": copy.deepcopy(_CUSTOMERS), "orders": []}


def _customer(state, customer_id):
    return state["customers"].get(customer_id)


def view_cart(state, customer_id):
    customer = _customer(state, customer_id)
    if customer is None:
        return {"ok": False, "error": "unknown customer"}
    return {"ok": True, "cart": copy.deepcopy(customer["cart"]), "coupon": customer["coupon"]}


def remove_item(state, customer_id, sku):
    customer = _customer(state, customer_id)
    if customer is None or not any(item["sku"] == sku for item in customer["cart"]):
        return {"ok": False, "error": "item not in cart"}
    customer["cart"] = [item for item in customer["cart"] if item["sku"] != sku]
    return {"ok": True}


def apply_coupon(state, customer_id, code):
    customer = _customer(state, customer_id)
    if customer is None or code not in COUPONS:
        return {"ok": False, "error": "unknown customer or coupon"}
    customer["coupon"] = code
    return {"ok": True}


def checkout(state, customer_id, address_label):
    customer = _customer(state, customer_id)
    if customer is None or not customer["cart"] or address_label not in customer["addresses"]:
        return {"ok": False, "error": "unknown customer, empty cart, or unknown address"}
    subtotal = sum(item["qty"] * item["price_cents"] for item in customer["cart"])
    discount = 0
    coupon = customer["coupon"]
    if coupon and subtotal >= COUPONS[coupon]["min_subtotal_cents"]:
        discount = subtotal * COUPONS[coupon]["percent"] // 100
    order = {"order_id": "SO-%d" % (7001 + len(state["orders"])), "customer_id": customer_id,
             "items": copy.deepcopy(customer["cart"]), "coupon": coupon, "subtotal_cents": subtotal,
             "discount_cents": discount, "total_cents": subtotal - discount,
             "ship_to": customer["addresses"][address_label]}
    state["orders"].append(order)
    customer["cart"], customer["coupon"] = [], None
    return {"ok": True, "order_id": order["order_id"], "total_cents": order["total_cents"]}


TOOLS = {"view_cart": view_cart, "remove_item": remove_item, "apply_coupon": apply_coupon, "checkout": checkout}
