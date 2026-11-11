# Schedule a budget review

Create a calendar event titled `Q4 budget review` on `2026-11-12` from `14:00` to `14:30`.

Invite exactly these three people and nobody else:

- Lena Ortiz (`lena.ortiz@example.com`)
- Sam Cho (`sam.cho@example.com`)
- Priya Nair (`priya.nair@example.com`)

Do not change any existing event.

Tools (see `support/env.py`):

- `find_person(name)`
- `list_events(date)`
- `create_event(title, date, start, end, attendees)`, where `attendees` is a list of email addresses
- `add_attendees(event_id, emails)`
