def _key(task):
    due = task["due"]
    return (task["priority"], due is None, due or "", task["title"])


def sort_tasks(tasks):
    return sorted(tasks, key=_key)
