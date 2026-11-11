import os
import shutil
import subprocess
import sys
import tempfile

TOOL = os.path.join("bin", "countlines")


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def run(directory, limit_s):
    try:
        proc = subprocess.run([TOOL, directory], capture_output=True, text=True, timeout=limit_s)
    except subprocess.TimeoutExpired:
        fail("bin/countlines took longer than %.1f s on %s" % (limit_s, os.path.basename(directory)))
    if proc.returncode != 0:
        fail("bin/countlines exited with %d: %s" % (proc.returncode, proc.stderr.strip()[:200]))
    return proc.stdout.strip()


if not os.path.isfile(TOOL) or not os.access(TOOL, os.X_OK):
    fail("bin/countlines is missing or not executable")
with open(TOOL, encoding="utf-8", errors="replace") as fh:
    if fh.readline().rstrip("\n") not in ("#!/usr/bin/env bash", "#!/bin/bash"):
        fail("bin/countlines must start with a bash shebang line")

scratch = tempfile.mkdtemp(prefix=".countlines-check-", dir=".")
try:
    small = os.path.join(scratch, "small")
    os.makedirs(os.path.join(small, "rotated"))
    write(os.path.join(small, "api.log"), "a\nb\nc\n")
    write(os.path.join(small, "worker.log"), "x\ny")
    write(os.path.join(small, "notes.txt"), "1\n2\n3\n4\n")
    write(os.path.join(small, "rotated", "api.log"), "old\nold\n")
    empty = os.path.join(scratch, "empty")
    os.makedirs(empty)
    big = os.path.join(scratch, "big")
    os.makedirs(big)
    expected_big = 0
    for i in range(3000):
        lines = 1 + i % 3
        expected_big += lines
        write(os.path.join(big, "shard-%04d.log" % i), "event %d\n" % i * lines)

    if run(small, 5) != "4":
        fail("bin/countlines small/ should print 4")
    if run(empty, 5) != "0":
        fail("bin/countlines on a directory without .log files should print 0")
    if run(big, 2.0) != str(expected_big):
        fail("bin/countlines big/ should print %d" % expected_big)
finally:
    shutil.rmtree(scratch, ignore_errors=True)

print("ok")
