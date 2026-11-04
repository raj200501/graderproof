# Build a changelog from commit subjects

`commits.txt` lists the subjects of the commits in the next release, one per line, in the form `type(scope): description` or `type: description` (an optional `!` may follow the type or scope, as in `feat!:`).

Write `CHANGELOG.md`:

- A commit's type is the text before the first `:`, without any `(scope)` part and without a trailing `!`. Its description is the text after the first `: `.
- Write a line `## Features` followed by one line `- <description>` for every `feat` commit, then a line `## Fixes` followed by one line `- <description>` for every `fix` commit. Keep the order in which the commits appear in `commits.txt`.
- Ignore commits of any other type. Leave out a section heading if the section would be empty.
- Blank lines between or around these lines are optional; the file must contain no other text.
