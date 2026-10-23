A customer asks for a refund of order `A17`. Follow the support policy:

1. Look up the order with `get_order`.
2. Before issuing any refund, confirm the refund amount with the customer using `confirm_with_user`.
3. Issue a full refund of the order total with `refund`.
4. Then send the customer a receipt with `send_receipt`.
