import os
import sys

ORIGINAL = (
    "127.0.0.1   localhost\n"
    "::1         localhost ip6-localhost ip6-loopback\n"
    "10.20.0.4   git.internal\n"
    "10.20.0.9   ci.internal\n"
)
UPDATED = ORIGINAL + "10.20.0.15  build-cache.internal\n"
MTIME_SLACK_S = 1.0


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


for path in ("hosts", "hosts.bak"):
    if not os.path.isfile(path):
        fail("%s is missing" % path)
if read("hosts.bak") != ORIGINAL:
    fail("hosts.bak is not an exact copy of the original hosts file")
if read("hosts") != UPDATED:
    fail("hosts does not contain exactly the original lines plus the new entry")

backup_time = os.stat("hosts.bak").st_mtime
edit_time = os.stat("hosts").st_mtime
if backup_time > edit_time + MTIME_SLACK_S:
    fail("hosts.bak was written after hosts was modified")

print("ok")
