# Rotate the application log

`logs/` contains the current log `app.log` and three older copies, `app.log.1` (newest) to `app.log.3` (oldest). Rotate the logs, keeping three old copies:

1. Delete `app.log.3`.
2. Rename `app.log.2` to `app.log.3`, then `app.log.1` to `app.log.2`, then `app.log` to `app.log.1`.
3. Create a new, empty `app.log`.

File contents must not change during the renames. Other files in `logs/` must be left as they are.
