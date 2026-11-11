#!/usr/bin/env python3
"""Audit which files a Claude Code subagent touched, from its JSONL transcript.

Used for the E0 planter (prereg/0001, docs/e0/planter_prompt.md) and for every
model-worker that answers an E0 request (DECISIONS.md D24): a worker may read only its
request file and write only its response file.

The audit reports paths and tool names only, never file content, so it can run on
transcripts that contain private material. For each transcript it lists the tool
calls by name, every Read/Write/Edit/Glob/Grep path outside the allowed prefixes, and
every absolute repository path a shell command mentions outside them.

Usage::

    python tools/transcript_audit.py --repo /path/to/repo --allow PREFIX ... T.jsonl ...

Exit status 0 when nothing outside the allowed prefixes was touched, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

FILE_TOOLS = ("Read", "Write", "Edit", "NotebookEdit")
SEARCH_TOOLS = ("Glob", "Grep")


def tool_uses(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """``(tool name, input)`` for every tool call in a transcript."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            content = (
                (event.get("message") or {}).get("content") if isinstance(event, dict) else None
            )
            if not isinstance(content, list):
                continue
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    yield str(c.get("name", "")), dict(c.get("input") or {})


def audit(path: Path, repo: str, allow: Sequence[str]) -> dict[str, Any]:
    """Tool counts and accesses outside ``allow`` for one transcript."""
    allowed = tuple(allow)
    names: Counter[str] = Counter()
    outside: Counter[str] = Counter()
    repo_re = re.compile(re.escape(repo.rstrip("/")) + r"/[\w./-]*")
    for name, inp in tool_uses(path):
        names[name] += 1
        if name in FILE_TOOLS:
            target = str(inp.get("file_path", ""))
            if not target.startswith(allowed):
                outside[f"{name} {target}"] += 1
        elif name in SEARCH_TOOLS:
            target = str(inp.get("path", "") or "")
            if not target or not target.startswith(allowed):
                outside[f"{name} {target or '<cwd>'}"] += 1
        elif name == "Bash":
            for token in repo_re.findall(str(inp.get("command", ""))):
                if not token.startswith(allowed):
                    outside[f"Bash {token}"] += 1
    return {
        "transcript": path.name,
        "tool_calls": dict(sorted(names.items())),
        "outside_allowed": dict(sorted(outside.items())),
        "clean": not outside,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; prints one JSON object per transcript."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcripts", nargs="+", type=Path)
    parser.add_argument("--repo", required=True, help="absolute repository path")
    parser.add_argument("--allow", action="append", default=[], help="allowed path prefix")
    args = parser.parse_args(argv)
    ok = True
    for t in args.transcripts:
        result = audit(t, args.repo, args.allow)
        ok = ok and result["clean"]
        print(json.dumps(result, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
