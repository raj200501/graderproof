# Edit distance for search suggestions

The search box suggests corrections for misspelled hotel names. Write a Python module `distance.py` with a function `levenshtein(a, b)` that returns the Levenshtein distance between the strings `a` and `b`: the minimum number of single-character insertions, deletions, and substitutions needed to turn `a` into `b`. Characters are compared exactly (case-sensitive), and each Unicode code point counts as one character.
