# URL slugs for article titles

Write a Python module `slug.py` with a function `slugify(title)` that turns an article title into a URL slug.

- Convert ASCII uppercase letters to lowercase.
- Keep ASCII letters and digits. Every maximal run of other characters (spaces, punctuation, non-ASCII letters such as `é`, and so on) becomes a single `-`.
- Remove any `-` at the start or end of the result.
- Return the slug as a string; it is `""` when the title has no ASCII letters or digits.

Examples: `slugify("Hello, World!")` returns `"hello-world"`, and `slugify("Café au lait")` returns `"caf-au-lait"`.
