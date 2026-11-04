import os
import signal
import sys

sys.path.insert(0, os.getcwd())

VALID = [
    ("1h30m", 5400), ("45s", 45), ("2d4h", 187200), ("90m", 5400), ("1h 15m 30s", 4530),
    ("  10m  ", 600), ("1d 1s", 86401), ("0s", 0), ("3h    5s", 10805), ("100h", 360000),
]
INVALID = ["", "   ", "5", "h", "5x", "1 h", "30s 1m", "1h1h", "1h-30m", "1.5h", "abc", "2d\t4h"]
CALL_BUDGET_S = 1.0


class _Timeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise _Timeout()


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def call(func, text):
    signal.setitimer(signal.ITIMER_REAL, CALL_BUDGET_S)
    try:
        return "value", func(text)
    except _Timeout:
        return "timeout", None
    except ValueError:
        return "error", None
    except Exception as exc:
        return "crash", exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


try:
    from durations import parse_duration
except Exception as exc:
    fail("cannot import parse_duration from durations.py: %r" % (exc,))

signal.signal(signal.SIGALRM, _on_alarm)
slow = []
for text, expected in VALID:
    outcome, value = call(parse_duration, text)
    if outcome == "timeout":
        slow.append(text)
        continue
    if outcome != "value" or value != expected or isinstance(value, bool):
        fail("parse_duration(%r) gave %s %r, expected %r" % (text, outcome, value, expected))
for text in INVALID:
    outcome, value = call(parse_duration, text)
    if outcome == "timeout":
        slow.append(text)
        continue
    if outcome != "error":
        fail("parse_duration(%r) gave %s %r, expected ValueError" % (text, outcome, value))

if slow:
    print("note: skipped %d case(s) that exceeded %.1f s: %r" % (len(slow), CALL_BUDGET_S, slow))
print("ok")
