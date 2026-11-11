# Count business days

Write a Python module `workdays.py` with a function `business_days(start, end, holidays=())` used to estimate delivery times.

- `start` and `end` are dates given as ISO strings (`YYYY-MM-DD`); `holidays` is an iterable of ISO date strings.
- Count the dates `d` with `start <= d < end` (the start date is included, the end date is not) that fall on Monday to Friday and are not in `holidays`.
- If `end` is not after `start`, return `0`.
- Return the count as an integer.
