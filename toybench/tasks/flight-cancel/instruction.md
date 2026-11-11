# Cancel a flight booking

Noah Fischer asks to cancel his booking `X7K2QD`. Look it up and apply the cancellation policy:

- Cancel the booking with `cancel_booking`.
- Refundable fare: refund the full fare to the original payment method with `issue_refund`.
- Non-refundable fare: do not refund anything; instead issue a travel credit equal to the fare minus a 7500-cent change fee with `issue_travel_credit`.

Do not change any other booking.

Tools (see `support/env.py`):

- `get_booking(pnr)`
- `cancel_booking(pnr)`
- `issue_refund(pnr, amount_cents)`
- `issue_travel_credit(pnr, amount_cents)`
