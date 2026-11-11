# Cancel a subscription with a partial refund

Ola Nordmann asks to cancel his meal-kit subscription `SUB-3381` right away.

1. Cancel `SUB-3381` immediately with `cancel_subscription` (`when` set to `immediately`, not at the end of the period).
2. Refund the unused part of the current period, 700 cents, with `issue_refund`.

Do not change any other subscription and issue no other refunds.

Tools (see `support/env.py`):

- `get_subscription(sub_id)`
- `cancel_subscription(sub_id, when)`, where `when` is `immediately` or `period_end`
- `issue_refund(sub_id, amount_cents)`
