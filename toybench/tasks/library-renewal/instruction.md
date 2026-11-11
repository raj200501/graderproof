# Renew library loans

Library member `M-1209` asks to renew everything that is due on or before `2026-11-10`.

Renew each of the member's loans due on or before `2026-11-10` exactly once with `renew_loan`, except loans whose title another member has placed a hold on (`list_loans` shows the holds). Do not renew any other loan.

Tools (see `support/env.py`):

- `list_loans(member_id)`
- `renew_loan(loan_id)`: extends the due date by 14 days
