# Find duplicate files

A cleanup tool needs to report files with identical contents. Write a Python module `dupes.py` with a function `duplicate_groups(files)`.

- `files` is a dict mapping a file path (a string) to that file's contents (a string).
- Two files are duplicates when their contents are exactly equal.
- Return a list of groups, one group for each content that is shared by two or more paths. A group is the sorted list of all paths with that content. Contents that belong to only one path produce no group.
- Order the groups by their first path. If there are no duplicates, return `[]`.
