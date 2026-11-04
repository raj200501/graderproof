# Team list as a Markdown table

Convert `team.csv` (a header row and one row per person; no field contains a comma or quotes) into a Markdown table in `team.md`.

- The first row of the table is the header row with the CSV column names, followed by a separator row, followed by one row per CSV record in the original order.
- Every row starts with `|` and ends with `|`, with cells separated by `|`. Spaces around cell text are optional and are ignored; cell text itself must be unchanged.
- Each separator cell consists of three or more `-` characters, optionally with a leading and/or trailing `:` for alignment.
- `team.md` contains only the table (a final newline is optional).
