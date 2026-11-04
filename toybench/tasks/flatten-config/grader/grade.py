import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

import copy

CASES = [
    (({"db": {"host": "x", "port": 5432}},), {"db.host": "x", "db.port": 5432}),
    (({"app": {"name": "booking", "features": ["search", "waitlist"], "limits": {"rps": 50, "burst": {}}},
       "debug": False, "empty": {}},), {"app.name": "booking", "app.features": ["search", "waitlist"],
                                       "app.limits.rps": 50, "debug": False}),
    (({"a": {"b": {"c": {"d": None}}}}, "__"), {"a__b__c__d": None}),
    (({},), {}),
    (({"x": 1, "y": {"z": [1, {"not": "flattened"}]}}, "/"), {"x": 1, "y/z": [1, {"not": "flattened"}]}),
]

try:
    from flatten import flatten
except Exception as exc:
    fail("cannot import flatten from flatten.py: %r" % (exc,))

for args, expected in CASES:
    before = copy.deepcopy(args[0])
    try:
        got = flatten(*args)
    except Exception as exc:
        fail("flatten%r raised %r" % (args, exc))
    if not isinstance(got, dict) or got != expected:
        fail("flatten%r = %r, expected %r" % (args, got, expected))
    if args[0] != before:
        fail("flatten modified its input: %r" % (args[0],))
    if got is args[0]:
        fail("flatten must return a new dict")

print("ok")
