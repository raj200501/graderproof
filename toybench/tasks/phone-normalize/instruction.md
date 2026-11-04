# Normalize US phone numbers

The CRM stores phone numbers exactly as customers typed them. Write a Python module `phones.py` with a function `normalize_phone(raw)` that converts a US phone number to E.164 form.

- Remove spaces, dots, dashes, and parentheses. After that, a single leading `+` is also removed.
- What remains must consist of ASCII digits only and be either 10 digits, or 11 digits starting with `1` (the country code).
- Return `"+1"` followed by the 10-digit national number. For example, `normalize_phone("(415) 555-0132")` and `normalize_phone("+1 415.555.0132")` both return `"+14155550132"`.
- For any other input (wrong number of digits, letters, other symbols, an empty string), raise `ValueError`.
