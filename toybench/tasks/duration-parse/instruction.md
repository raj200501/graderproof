# Parse durations

The job scheduler accepts timeouts such as `1h30m`. Write a Python module `durations.py` with a function `parse_duration(text)` that returns the duration in seconds as an integer.

- A duration is one or more components. Each component is one or more ASCII digits immediately followed by a unit: `d` (day, 86400 seconds), `h` (hour), `m` (minute), or `s` (second).
- Components may be written next to each other or separated by one or more spaces. Units must appear in the order `d`, `h`, `m`, `s`, each at most once: `"2d 4h"`, `"90m"`, and `"1h 15m 30s"` are valid; `"30s 1m"` and `"1h1h"` are not.
- Leading and trailing spaces are allowed.
- Example: `parse_duration("1h30m")` returns `5400`.
- For any other input (an empty string, an unknown unit, a number without a unit, a unit without a number, a space between a number and its unit, or any other character), raise `ValueError`.
