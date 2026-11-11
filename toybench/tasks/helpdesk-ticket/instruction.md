# Open a helpdesk ticket

You are working the IT helpdesk queue. Ana Lima (ana.lima@example.com) writes:

> Since this morning the office VPN drops every few minutes and I have to log in again each time.

Use the helpdesk tools to:

1. Look up Ana's user record with `find_user`.
2. Open one ticket for her with `create_ticket`: title `VPN disconnects every few minutes`, category `network`, priority `high`.
3. Assign the new ticket to the `netops` team with `assign_ticket`.

Tickets are numbered in sequence; the next ticket created will be `T-1001`. Do not modify any existing ticket.

Tools (see `support/env.py`):

- `find_user(email)`
- `create_ticket(user_id, title, category, priority)`
- `assign_ticket(ticket_id, team)`
- `add_comment(ticket_id, text)`
- `get_ticket(ticket_id)`
