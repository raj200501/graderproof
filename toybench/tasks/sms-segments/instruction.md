# Split long text messages

The SMS gateway sends long texts as multi-part messages, and each part of a multi-part message holds at most 153 characters. Write a Python module `sms.py` with a function `split_sms(message)` that returns the list of parts to send:

- If `message` has at most 160 characters, return `[message]` (a single, unsplit message). This includes the empty message, which returns `[""]`.
- Otherwise split it into consecutive parts of exactly 153 characters, except the last part, which holds the remaining 1 to 153 characters.
- Joining the parts in order must give back `message` exactly: do not strip, add, reorder, or change any character.
