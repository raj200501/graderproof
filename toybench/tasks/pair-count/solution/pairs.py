from collections import Counter


def count_pairs(nums, target):
    seen = Counter()
    count = 0
    for value in nums:
        count += seen[target - value]
        seen[value] += 1
    return count
