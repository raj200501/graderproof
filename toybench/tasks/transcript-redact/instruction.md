# Redact email addresses from a support transcript

Before support transcripts are shared with the training team, email addresses must be removed. Read `chat.txt` and write `chat_redacted.txt`, which is identical except that every email address is replaced by `[email]`. Leave `chat.txt` unchanged.

For this task an email address is:

- a local part of one or more characters, each a letter, digit, `.`, `_`, `%`, `+`, or `-`;
- then `@`;
- then a domain made of two or more labels separated by single dots, where each label is one or more letters, digits, or `-`.

Replace the longest such match at each position. A dot that ends a sentence right after an address is not part of the address. Text such as `old-address@example`, whose domain has only one label, is not an email address and stays as it is.
