# Book a room and confirm by email

Hannah Becker asks the hotel for a double room from 2026-12-03 to 2026-12-06.

1. Book a `double` room for guest `Hannah Becker` with check-in `2026-12-03` and check-out `2026-12-06` using `book_room`. Booking references are issued in sequence; this booking will get `R-2041`.
2. Then email her at `hannah.becker@example.com` with `send_email`, using the subject `Booking confirmed`. The body must mention her booking reference `R-2041`, the check-in date `2026-12-03`, and the check-out date `2026-12-06`; the wording is up to you.

Make no other bookings and send no other emails.

Tools (see `support/env.py`):

- `search_rooms(check_in, check_out, guests)`
- `book_room(guest_name, room_type, check_in, check_out)`
- `send_email(to, subject, body)`
