# Downgrade a subscription plan

Kofi Mensah wants to move account `AC-4410` from the Pro plan to the Basic plan at the end of the current billing period, not immediately.

- Policy: before scheduling any plan change, verify the account holder with `verify_account`. He gave the ZIP code `60614`.
- Schedule the change to plan `basic` with `effective` set to `period_end` using `schedule_plan_change`.
- Add an account note about the downgrade with `add_note`; the note text must contain the word `downgrade` (any capitalization).

Do not change any other account.

Tools (see `support/env.py`):

- `verify_account(account_id, zip_code)`
- `get_account(account_id)`
- `schedule_plan_change(account_id, plan, effective)`, where `effective` is `now` or `period_end`
- `add_note(account_id, text)`
