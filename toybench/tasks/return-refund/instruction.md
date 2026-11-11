# Refund a returned item

The warehouse confirms that the parcel for return `RMA-7712` (trail running shoes from order `ORD-61200`) arrived and the shoes are in good condition.

1. Mark the return as received with `mark_received`, condition `good`.
2. Refund it to the original payment method with `refund_rma`. The refund must actually be issued.

Do not change any other return.

Tools (see `support/env.py`):

- `get_rma(rma_id)`
- `mark_received(rma_id, condition)`, where `condition` is `good` or `damaged`
- `refund_rma(rma_id)`: only possible for a return received in good condition
