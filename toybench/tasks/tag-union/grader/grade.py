import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    (
        [{"title": "Sourdough basics", "tags": ["Baking", "bread", " Fermentation "]},
         {"title": "Rye starter", "tags": ["bread", "RYE", "baking"]},
         {"title": "Kitchen scales", "tags": ["equipment", "", "  "]},
         {"title": "Focaccia", "tags": ["Bread", "italian"]}],
        ["baking", "bread", "fermentation", "rye", "equipment", "italian"],
    ),
    ([{"tags": ["Zeta", "alpha", "Mu"]}, {"tags": ["ALPHA"]}], ["zeta", "alpha", "mu"]),
    ([{"tags": []}], []),
    ([], []),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from tagging import all_tags
except Exception as exc:
    fail("cannot import all_tags from tagging.py: %r" % (exc,))

for posts, expected in CASES:
    try:
        got = all_tags(posts)
    except Exception as exc:
        fail("all_tags raised %r" % (exc,))
    if not isinstance(got, list):
        fail("all_tags must return a list, got %s" % type(got).__name__)
    if got != expected:
        fail("all_tags returned %r, expected %r" % (got, expected))

print("ok")
