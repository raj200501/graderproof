import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

with open("chat.txt", encoding="utf-8", newline="") as fh:
    text = fh.read()
with open("chat_redacted.txt", "w", encoding="utf-8", newline="") as fh:
    fh.write(EMAIL.sub("[email]", text))
