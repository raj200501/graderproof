# Order a task list

Write a Python module `taskqueue.py` with a function `sort_tasks(tasks)` for a to-do app.

- `tasks` is a list of dicts. Each dict has a `title` (string), a `priority` (integer, 1 is the most urgent), and a `due` date (an ISO `YYYY-MM-DD` string, or `None` when there is no due date). Dicts may contain other keys, which must be kept.
- Return a new list with the same dicts ordered by priority (1 first), then by due date (earliest first, tasks without a due date after those with one), then by title (alphabetical, case-sensitive).
- The caller keeps using its own list: `sort_tasks` must not modify the input list or any of the dicts in it.
