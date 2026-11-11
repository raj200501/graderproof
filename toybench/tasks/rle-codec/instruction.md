# Run-length encoding

Write a Python module `rle.py` with two functions.

- `encode(s)`: `s` is a string that contains no decimal digits. Replace each maximal run of one repeated character by the run length in decimal (no leading zeros) followed by that character. For example, `encode("aaab")` returns `"3a1b"`, `encode("a" * 12)` returns `"12a"`, and `encode("")` returns `""`. Spaces, newlines, and other characters are encoded like any other character.
- `decode(code)`: the inverse. `code` is a sequence of pairs, each a positive decimal count without leading zeros followed by one character that is not a digit; the result repeats each character count times, so `decode("3a1b")` returns `"aaab"` and `decode("")` returns `""`. Raise `ValueError` if `code` is not of this form (for example `"a3"`, `"3"`, `"0a"`, or `"03a"`).
