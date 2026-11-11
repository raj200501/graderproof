# Edit a cart and check out

Customer `CU-310` asks you to finish their order:

1. Remove the mug (SKU `MUG-02`) from the cart.
2. Apply the coupon `WINTER10`.
3. Check out to the saved address labeled `office`.

Leave the other items and their quantities as they are.

Tools (see `support/env.py`):

- `view_cart(customer_id)`
- `remove_item(customer_id, sku)`
- `apply_coupon(customer_id, code)`
- `checkout(customer_id, address_label)`
