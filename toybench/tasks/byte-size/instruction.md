# Human-readable file sizes

Write a Python module `sizes.py` with a function `format_size(n)` for the file browser, where `n` is a non-negative integer number of bytes.

- If `n` is less than 1024, return the number followed by ` B`, for example `"0 B"` or `"1023 B"`.
- Otherwise choose the largest unit among `KiB` (1024 bytes), `MiB` (1024² bytes), `GiB` (1024³ bytes), and `TiB` (1024⁴ bytes) that is not larger than `n`, divide `n` by it, and write the result with exactly one decimal place, a space, and the unit, for example `format_size(1536)` returns `"1.5 KiB"`. Sizes of 1024 TiB or more are still written in TiB.
- Round to one decimal place with halves rounded up (1280 bytes is `"1.3 KiB"`). The unit is chosen before rounding, so 1048575 bytes is `"1024.0 KiB"`.
