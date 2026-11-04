import os
import sys

sys.path.insert(0, os.getcwd())

CASES = [
    (set(), 8000, 8010, True),
    ({8000, 8001, 8002}, 8000, 8010, True),
    ({5432}, 5432, 5440, True),
    ({9000, 9001}, 9000, 9001, False),
    ({3000, 3002, 3004}, 3000, 3005, True),
    ({7000}, 7000, 7000, False),
    (set(range(6000, 6050)) - {6020, 6050}, 6000, 6050, True),
    ({4001, 4002, 4003}, 4000, 4003, True),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from ports import pick_port
except Exception as exc:
    fail("cannot import pick_port from ports.py: %r" % (exc,))

for used, low, high, has_free in CASES:
    try:
        port = pick_port(set(used), low, high)
    except Exception as exc:
        fail("pick_port(..., %d, %d) raised %r" % (low, high, exc))
    if not has_free:
        if port is not None:
            fail("pick_port(..., %d, %d) = %r, expected None (range is full)" % (low, high, port))
        continue
    if isinstance(port, bool) or not isinstance(port, int):
        fail("pick_port(..., %d, %d) = %r, expected a port number" % (low, high, port))
    if not low <= port < high:
        fail("pick_port(..., %d, %d) = %d is outside the range" % (low, high, port))
    if port in used:
        fail("pick_port(..., %d, %d) = %d is already in use" % (low, high, port))

print("ok")
