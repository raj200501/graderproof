# Change a shipping address

Customer Iain Murray emails that he has moved. His order `ORD-55120` has not shipped yet.

Use `update_shipping_address` to set the shipping address of order `ORD-55120` to exactly this one-line string:

`Flat 3, 14 Harbour Street, Leith, Edinburgh EH6 6QP`

Do not change any other order, and do not change any other field of this order.

Tools (see `support/env.py`):

- `get_order(order_id)`
- `update_shipping_address(order_id, address)` (only possible while the order is `processing`)
