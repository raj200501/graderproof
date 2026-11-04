# Restaurant reservation

A caller asks for a dinner reservation. Use the reservation tools to book a table with these details:

- name: `Priya Raman`
- phone: `+44 20 7946 0321`
- date: `2026-11-14`, time: `19:30`
- party size: 4
- notes: `wheelchair access`

Make exactly one new reservation and leave all existing reservations as they are.

Tools (see `support/env.py`):

- `check_availability(date, time, party_size)`
- `create_reservation(name, phone, date, time, party_size, notes)`
- `cancel_reservation(reservation_id)`
- `list_reservations(date)`
