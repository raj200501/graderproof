# Renew a residential parking permit

Dana Kowalski (customer `CU-5521`) wants to renew the residential parking permit for her car, plate `KX-482-LM`.

1. Look up the permit by plate with `lookup_permit`. Her permit is `PRM-7730`.
2. Renew it for 12 months with `renew_permit`, which extends the expiry date by the given number of months.
3. Charge her card on file 9600 cents (12 months at $8.00) with `charge_card`, using the description `permit renewal PRM-7730`.

Do not change any other permit and do not make any other charge.

Tools (see `support/env.py`):

- `lookup_permit(plate)`
- `renew_permit(permit_id, months)`
- `charge_card(customer_id, amount_cents, description)`
