import math
import os
import sys

sys.path.insert(0, os.getcwd())

BASE = (
    "Your parcel 4471-KD is out for delivery today between 13:00 and 17:00. "
    "Reply STOP to opt out. If nobody is home we will leave it with a neighbour "
    "or at the depot on Mill Lane (open 08:00-20:00, ID required). "
)
CASES = ["", "Hi!", BASE[:160], BASE[:161], BASE[:200], (BASE * 2)[:306], (BASE * 2)[:307], (BASE * 3)[:500]]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from sms import split_sms
except Exception as exc:
    fail("cannot import split_sms from sms.py: %r" % (exc,))

for message in CASES:
    try:
        parts = split_sms(message)
    except Exception as exc:
        fail("split_sms raised %r for a %d-character message" % (exc, len(message)))
    if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
        fail("split_sms must return a list of strings")
    n = len(message)
    expected_parts = 1 if n <= 160 else math.ceil(n / 153)
    if len(parts) != expected_parts:
        fail("%d-character message: expected %d parts, got %d" % (n, expected_parts, len(parts)))
    if n <= 160:
        if len(parts[0]) != n:
            fail("%d-character message must be sent as one unsplit part" % n)
        continue
    if any(len(p) != 153 for p in parts[:-1]):
        fail("%d-character message: every part but the last must have 153 characters" % n)
    if not 1 <= len(parts[-1]) <= 153:
        fail("%d-character message: the last part has %d characters" % (n, len(parts[-1])))

print("ok")
