# Strip trailing whitespace from the source tree

The linter rejects lines that end in whitespace. Clean up the project in the working directory:

- For every `.py` file under `src/` (including subdirectories), remove all spaces and tabs at the end of every line.
- Change nothing else in those files: keep the line order, indentation, blank lines, and whether or not the file ends with a newline.
- Do not modify any file outside `src/`, and do not modify files under `src/` that are not `.py` files. In particular, `vendor/` holds third-party code that must stay byte-for-byte identical.
