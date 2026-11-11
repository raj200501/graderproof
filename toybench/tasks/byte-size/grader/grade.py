import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    (0, "0 B"), (1, "1 B"), (1023, "1023 B"), (1024, "1.0 KiB"), (1280, "1.3 KiB"), (1536, "1.5 KiB"),
    (10 * 1024 - 1, "10.0 KiB"), (1048575, "1024.0 KiB"), (1048576, "1.0 MiB"), (5000000, "4.8 MiB"),
    (734003200, "700.0 MiB"), (1073741824, "1.0 GiB"), (3 * 1024 ** 4 + 1024 ** 3 * 512, "3.5 TiB"),
    (5 * 1024 ** 5, "5120.0 TiB"), (123456789, "117.7 MiB"),
]

try:
    from sizes import format_size
except Exception as exc:
    fail("cannot import format_size from sizes.py: %r" % (exc,))

for n, expected in CASES:
    try:
        got = format_size(n)
    except Exception as exc:
        fail("format_size(%d) raised %r" % (n, exc))
    if got != expected:
        fail("format_size(%d) = %r, expected %r" % (n, got, expected))

print("ok")
