#!/usr/bin/env python3
"""Style rule from docs/BUILD_BRIEF.md rule 12: no em dashes in any tracked text file.

Verbatim third-party material (tests/fixtures/, third_party/) is exempt because it is
not Claude's writing. Exit status 1 lists every offending file and line.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)  # spelled as a code point so this file passes its own check
EXEMPT_PREFIXES = ("tests/fixtures/", "third_party/")


def tracked_files(repo: Path) -> list[str]:
    """Tracked paths relative to ``repo``."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode()
    return [p for p in out.split("\0") if p]


def find_em_dashes(repo: Path, paths: list[str]) -> list[str]:
    """Return ``path:line`` for every line containing an em dash, skipping exempt paths."""
    hits: list[str] = []
    for rel in paths:
        if rel.startswith(EXEMPT_PREFIXES):
            continue
        path = repo / rel
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                hits.append(f"{rel}:{i}")
    return hits


def main() -> int:
    hits = find_em_dashes(REPO, tracked_files(REPO))
    for h in hits:
        print(f"em dash: {h}")
    if hits:
        print(f"style-check: FAIL ({len(hits)} lines with em dashes)")
        return 1
    print("style-check: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
