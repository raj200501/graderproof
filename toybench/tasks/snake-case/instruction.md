# camelCase to snake_case

Write a Python module `naming.py` with a function `to_snake(name)` used when generating database column names. `name` is a non-empty identifier made of ASCII letters and digits, in camelCase or PascalCase, possibly containing acronyms.

- Insert `_` before an uppercase letter whose previous character is a lowercase letter or a digit.
- Also insert `_` before an uppercase letter that is preceded by an uppercase letter and followed by a lowercase letter (this separates an acronym from the next word).
- Then convert the whole result to lowercase.

Examples: `"userId"` gives `"user_id"`, `"HTTPServer"` gives `"http_server"`, and `"getHTTPResponseCode"` gives `"get_http_response_code"`.
