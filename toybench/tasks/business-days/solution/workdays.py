from datetime import date, timedelta


def business_days(start, end, holidays=()):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    skip = {date.fromisoformat(h) for h in holidays}
    count = 0
    day = first
    while day < last:
        if day.weekday() < 5 and day not in skip:
            count += 1
        day += timedelta(days=1)
    return count
