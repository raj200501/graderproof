# Word wrapping

Write a Python module `wrap.py` with a function `wrap(text, width)` that wraps text for a fixed-width terminal. `width` is a positive integer.

- Words are the maximal runs of non-whitespace characters in `text`.
- Fill lines greedily: put words on the current line, separated by single spaces, as long as the line stays at most `width` characters long; when the next word does not fit, start a new line with it.
- A word longer than `width` is put on a line of its own, unbroken.
- Return the list of lines. No line has leading or trailing spaces. If `text` contains no words, return `[]`.
