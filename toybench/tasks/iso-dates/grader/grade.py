import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())

CASES = [
    ("March 5, 2026", "2026-03-05"), ("Mar 5, 2026", "2026-03-05"), ("DECEMBER 31, 2025", "2025-12-31"),
    ("sep 9, 2026", "2026-09-09"), ("05/03/2026", "2026-03-05"), ("29/02/2028", "2028-02-29"),
    ("2026.03.05", "2026-03-05"), ("  2026.11.04 ", "2026-11-04"), ("July 14, 2026", "2026-07-14"),
]
INVALID = ["", "2026-03-05", "31/04/2026", "5/3/2026", "Smarch 5, 2026", "March 5 2026", "2026.13.01",
           "29/02/2027", "next Tuesday"]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from dateparse import to_iso_date
except Exception as exc:
    fail("cannot import to_iso_date from dateparse.py: %r" % (exc,))

for text, expected in CASES:
    try:
        got = to_iso_date(text)
    except Exception as exc:
        fail("to_iso_date(%r) raised %r" % (text, exc))
    try:
        parsed = date.fromisoformat(got)
    except (TypeError, ValueError):
        continue
    if got != expected or parsed != date.fromisoformat(expected):
        fail("to_iso_date(%r) = %r, expected %r" % (text, got, expected))

for text in INVALID:
    try:
        to_iso_date(text)
    except ValueError:
        continue
    except Exception as exc:
        fail("to_iso_date(%r) raised %r, expected ValueError" % (text, exc))
    fail("to_iso_date(%r) did not raise ValueError" % text)

print("ok")
