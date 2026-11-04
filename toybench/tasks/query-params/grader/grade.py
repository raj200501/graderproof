import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    ("?q=red+shoes&size=42&sort=price%2Basc", {"q": "red shoes", "size": "42", "sort": "price+asc"}),
    ("name=Ren%C3%A9e&city=Montr%C3%A9al", {"name": "Renée", "city": "Montréal"}),
    ("debug&page=2&page=3", {"debug": "", "page": "3"}),
    ("a=1&&b=2&", {"a": "1", "b": "2"}),
    ("redirect=%2Fhome%3Ftab%3D2&x=a=b", {"redirect": "/home?tab=2", "x": "a=b"}),
    ("first%20name=Jo+Ann", {"first name": "Jo Ann"}),
    ("", {}),
    ("?", {}),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from urlquery import parse_query
except Exception as exc:
    fail("cannot import parse_query from urlquery.py: %r" % (exc,))

for qs, expected in CASES:
    try:
        got = parse_query(qs)
    except Exception as exc:
        fail("parse_query(%r) raised %r" % (qs, exc))
    if not isinstance(got, dict):
        fail("parse_query(%r) returned %s, expected a dict" % (qs, type(got).__name__))
    if set(got) != set(expected):
        fail("parse_query(%r) has keys %s, expected %s" % (qs, sorted(got), sorted(expected)))
    for key, value in got.items():
        if not isinstance(value, str):
            fail("parse_query(%r)[%r] is %r, expected a string" % (qs, key, value))

print("ok")
