import re

SUBJECT = re.compile(r"^([A-Za-z]+)(\([^)]*\))?!?: (.*)$")
sections = {"feat": [], "fix": []}
with open("commits.txt", encoding="utf-8") as fh:
    for line in fh.read().split("\n"):
        match = SUBJECT.match(line)
        if match and match.group(1) in sections:
            sections[match.group(1)].append(match.group(3))

out = []
for kind, title in (("feat", "## Features"), ("fix", "## Fixes")):
    if sections[kind]:
        out.append(title)
        out.extend("- " + description for description in sections[kind])
        out.append("")
with open("CHANGELOG.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
