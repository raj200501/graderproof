# Allocate a free port

The test harness starts services on free ports. Write a Python module `ports.py` with a function `pick_port(used, low, high)`.

- `used` is a set of port numbers that are taken; `low` and `high` are integers with `low <= high`.
- Return any port `p` with `low <= p <= high` (both ends included) that is not in `used`. Any such port is acceptable.
- If every port in the range is taken, return `None`.
