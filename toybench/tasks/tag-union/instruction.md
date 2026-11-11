# Collect blog tags

The blog's sidebar shows every tag used on the site. Write a Python module `tagging.py` with a function `all_tags(posts)`.

- `posts` is a list of dicts; each has a key `tags` whose value is a list of strings.
- Normalize each tag by removing surrounding whitespace and converting it to lowercase. Ignore tags that are empty after this.
- Return a list containing each distinct normalized tag exactly once. The order of the returned list does not matter.
