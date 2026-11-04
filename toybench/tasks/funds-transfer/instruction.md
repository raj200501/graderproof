# Move money to savings

Jonah Weiss (customer `C-118`) calls the bank: he wants to move $250.00 from his checking account to his savings account, with the memo `holiday fund`.

Use the banking tools to make exactly one transfer of 25000 cents from his checking account `ACC-3301` to his savings account `ACC-3302`, with memo `holiday fund`. Do not move money into or out of any other account.

Tools (see `support/env.py`):

- `list_accounts(customer_id)`
- `get_balance(account_id)`
- `transfer(from_account, to_account, amount_cents, memo)`
