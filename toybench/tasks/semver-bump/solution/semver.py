import re

_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def bump(version, part):
    match = _VERSION.fullmatch(version)
    if match is None:
        raise ValueError("invalid version: %r" % (version,))
    major, minor, patch = (int(g) for g in match.groups())
    if part == "major":
        return "%d.0.0" % (major + 1)
    if part == "minor":
        return "%d.%d.0" % (major, minor + 1)
    if part == "patch":
        return "%d.%d.%d" % (major, minor, patch + 1)
    raise ValueError("unknown part: %r" % (part,))
