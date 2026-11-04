import os
import sqlite3
import sys


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


if not os.path.isfile("schema.sql"):
    fail("schema.sql was not created")
with open("schema.sql", encoding="utf-8") as fh:
    sql = fh.read()
if not sql.strip():
    fail("schema.sql is empty")

conn = sqlite3.connect(":memory:")
try:
    conn.executescript(sql)
except sqlite3.Error as exc:
    fail("schema.sql does not run on an empty database: %s" % exc)

if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    fail("database integrity check failed after running schema.sql")
conn.execute("PRAGMA foreign_keys = ON")
if conn.execute("PRAGMA foreign_key_check").fetchall():
    fail("foreign key check failed after running schema.sql")
conn.close()

print("ok")
