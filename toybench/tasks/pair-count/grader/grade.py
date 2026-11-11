import os
import random
import sys
import time
from collections import Counter

sys.path.insert(0, os.getcwd())

CASES = [
    (([1, 5, 7, -1, 5], 6), 3),
    (([], 4), 0),
    (([4], 8), 0),
    (([2, 2, 2, 2], 4), 6),
    (([3, -3, 0, 0, 6, -6], 0), 3),
    (([10, 20, 30], 100), 0),
    (([-5, -1, -4, 0, 1], -5), 2),
]
TIME_LIMIT_S = 0.05


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def reference_count(nums, target):
    counts = Counter(nums)
    total = 0
    for value, c in counts.items():
        other = target - value
        if value < other:
            total += c * counts.get(other, 0)
        elif value == other:
            total += c * (c - 1) // 2
    return total


try:
    from pairs import count_pairs
except Exception as exc:
    fail("cannot import count_pairs from pairs.py: %r" % (exc,))

for (nums, target), expected in CASES:
    try:
        got = count_pairs(list(nums), target)
    except Exception as exc:
        fail("count_pairs(%r, %r) raised %r" % (nums, target, exc))
    if got != expected:
        fail("count_pairs(%r, %r) = %r, expected %r" % (nums, target, got, expected))

rng = random.Random(20261104)
big = [rng.randint(-2000, 2000) for _ in range(5000)]
expected = reference_count(big, 37)
start = time.perf_counter()
got = count_pairs(list(big), 37)
elapsed = time.perf_counter() - start
if got != expected:
    fail("count_pairs on 5000 values = %r, expected %r" % (got, expected))
if elapsed > TIME_LIMIT_S:
    fail("count_pairs on 5000 values took %.3f s (limit %.2f s)" % (elapsed, TIME_LIMIT_S))

print("ok")
