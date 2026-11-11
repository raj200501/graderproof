# Book the cheapest matching room

Elif Demir wants a room from `2026-12-18` (check-in) to `2026-12-20` (check-out).

Book the cheapest room that is available for those dates, is non-smoking, and has a king bed. Book it under the guest name `Elif Demir` and attach her loyalty number `LY-55821`. Make no other bookings or changes.

Tools (see `support/env.py`):

- `search_rooms(check_in, check_out)`: rooms available for the whole stay, with bed type, smoking flag, and nightly price
- `create_booking(room, guest_name, check_in, check_out, loyalty_number)`
- `cancel_booking(booking_id)`
