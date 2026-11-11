# Card number check

Write a Python module `luhn.py` with a function `luhn_valid(number)` used to catch typos in card numbers before they are sent to the payment provider.

- `number` is a string. Spaces and dashes are allowed as group separators and are removed first.
- Return `True` if what remains consists only of ASCII digits, has 12 to 19 digits, and passes the Luhn checksum: starting from the rightmost digit and moving left, double every second digit (subtracting 9 from any result above 9), add up all the digits, and check that the sum is divisible by 10.
- Return `False` in every other case, including empty input and input with other characters. Never raise an exception for a string argument.
