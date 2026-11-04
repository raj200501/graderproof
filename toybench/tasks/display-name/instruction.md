# Correct a staff directory profile

HR forwarded a request from user `U-7781`: their name was entered in capitals and without their middle initial, and their pronouns are missing.

Using the directory tools, set the `display_name` of user `U-7781` to exactly `Maya R. Okafor` (with this capitalization, spacing, and punctuation) and set their `pronouns` to exactly `she/her`. Do not change any other field or any other user.

Tools (see `support/env.py`):

- `get_profile(user_id)`
- `update_profile(user_id, field, value)`, where `field` is one of `display_name`, `pronouns`, `title`, `phone`
