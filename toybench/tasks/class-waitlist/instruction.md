# Swap a fitness class for a waitlist spot

Gym member `G-208` can no longer attend Tuesday's yoga class `CL-TUE-YOGA`. Cancel that booking, and add the member to the waitlist of Thursday's yoga class `CL-THU-YOGA`, which is full. Do not change anything else.

Tools (see `support/env.py`):

- `list_classes()`
- `cancel_booking(member_id, class_id)`
- `book_class(member_id, class_id)`: fails when the class is full
- `join_waitlist(member_id, class_id)`: adds the member to the end of the waitlist
