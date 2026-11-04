_PAIRS = {")": "(", "]": "[", "}": "{"}


def is_balanced(s):
    stack = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in _PAIRS:
            if not stack or stack.pop() != _PAIRS[ch]:
                return False
    return not stack
