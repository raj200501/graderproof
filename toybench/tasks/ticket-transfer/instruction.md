# Transfer concert tickets

Imani Clarke (account `TK-9035`) wants to give the tickets for seats `A12` and `A13` of "Jazz at the Pier" to her friend at `rafael.ortiz@example.com`. Seats `A10` and `A11` stay on her account.

Ticket transfers require verification: call `send_verification_code` for her account, then `confirm_verification` with the code she reads back to you, which is `481516`. Transfer tickets only after the verification has succeeded.

Tools (see `support/env.py`):

- `list_tickets(account_id)`
- `send_verification_code(account_id)`
- `confirm_verification(account_id, code)`
- `transfer_ticket(ticket_id, recipient_email)`
