# Count pairs with a given sum

Write a Python module `pairs.py` with a function `count_pairs(nums, target)` that returns the number of index pairs `(i, j)` with `i < j` and `nums[i] + nums[j] == target`.

- `nums` is a list of at most 5,000 integers; values may be negative and may repeat. `target` is an integer.
- Example: `count_pairs([1, 5, 7, -1, 5], 6)` returns `3` (1 + 5, 7 + (-1), and 1 + the second 5).
- An empty list or a list with one element gives `0`.
