import copy
import os
import sys

sys.path.insert(0, os.getcwd())


def t(title, priority, due, **extra):
    return dict(title=title, priority=priority, due=due, **extra)


CASES = [
    (
        [t("Renew passport", 2, "2026-12-01"), t("Pay rent", 1, "2026-11-30"), t("Call plumber", 1, None),
         t("Book flights", 2, "2026-11-20", tags=["travel"]), t("Answer email", 1, "2026-11-30"),
         t("Water plants", 3, None), t("Archive photos", 3, None)],
        ["Answer email", "Pay rent", "Call plumber", "Book flights", "Renew passport", "Archive photos",
         "Water plants"],
    ),
    ([t("b", 1, None), t("B", 1, None), t("a", 1, None)], ["B", "a", "b"]),
    ([t("Only task", 4, "2027-01-15", owner="sam")], ["Only task"]),
    ([], []),
]


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    from taskqueue import sort_tasks
except Exception as exc:
    fail("cannot import sort_tasks from taskqueue.py: %r" % (exc,))

for tasks, order in CASES:
    by_title = {task["title"]: copy.deepcopy(task) for task in tasks}
    expected = [by_title[title] for title in order]
    try:
        result = sort_tasks(tasks)
    except Exception as exc:
        fail("sort_tasks raised %r" % (exc,))
    if not isinstance(result, list):
        fail("sort_tasks must return a list")
    titles = [task.get("title") if isinstance(task, dict) else task for task in result]
    if titles != order:
        fail("order is %r, expected %r" % (titles, order))
    if result != expected:
        fail("the returned tasks differ from the input tasks (keys or values changed)")

print("ok")
