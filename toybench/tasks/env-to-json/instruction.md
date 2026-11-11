# Convert an env file to JSON

The deployment tool wants its settings as JSON. Convert `app.env` into `config.json`.

Rules for reading `app.env`:

- Ignore blank lines and lines whose first non-space character is `#`.
- Every other line has the form `KEY=VALUE`, split at the first `=`. Remove spaces and tabs around the key and around the value.
- If the value (after that) starts and ends with the same quote character, `"` or `'`, remove that pair of quotes. Nothing else is unescaped.
- If a key appears more than once, the last occurrence wins.

`config.json` must contain a JSON object mapping each key to its value as a string. Formatting and key order are up to you.
