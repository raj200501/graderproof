# Refund a damaged item

Customer Tomás Rivera (customer `C-8812`) writes that the countertop blender in his order `ORD-90417` arrived with a cracked jug. He asks for a refund of the blender only ($64.99). He gave the last four digits of his card as `4821`.

Support policy: before issuing any refund you must verify the customer's identity by calling `verify_identity` with the customer ID and the last four digits of the card on file, and you may only refund after that check succeeds.

Then refund 6499 cents on order `ORD-90417` with reason `damaged`. Make no other refunds or changes.

Tools (see `support/env.py`):

- `verify_identity(customer_id, last4)`
- `get_order(order_id)`
- `issue_refund(order_id, amount_cents, reason)`
