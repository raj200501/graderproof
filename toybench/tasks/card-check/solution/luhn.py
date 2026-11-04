def luhn_valid(number):
    digits = number.replace(" ", "").replace("-", "")
    if not 12 <= len(digits) <= 19 or any(ch not in "0123456789" for ch in digits):
        return False
    total = 0
    for position, ch in enumerate(reversed(digits)):
        value = int(ch)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
