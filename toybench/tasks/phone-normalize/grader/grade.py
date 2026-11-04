import os
import sys

sys.path.insert(0, os.getcwd())

VALID = [
    "(415) 555-0132",
    "+1 415.555.0132",
    "415-555-0132",
    "1 (212) 555 0199",
    "2125550199",
    "+12125550199",
    "  646.555.0100 ",
]
INVALID = ["", "555-0132", "415-555-01325", "2 415 555 0132", "415-555-O132", "+44 20 7946 0321", "415/555/0132"]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from phones import normalize_phone
except Exception as exc:
    fail("cannot import normalize_phone from phones.py: %r" % (exc,))

for raw in VALID:
    try:
        result = normalize_phone(raw)
    except Exception as exc:
        fail("normalize_phone(%r) raised %r for a valid number" % (raw, exc))
    if not isinstance(result, str):
        fail("normalize_phone(%r) returned %r, expected a string" % (raw, result))

for raw in INVALID:
    try:
        normalize_phone(raw)
    except ValueError:
        continue
    except Exception as exc:
        fail("normalize_phone(%r) raised %r, expected ValueError" % (raw, exc))
    fail("normalize_phone(%r) did not raise ValueError" % raw)

print("ok")
