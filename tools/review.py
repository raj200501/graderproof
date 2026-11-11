#!/usr/bin/env python3
"""Independent review (`make review`, docs/BUILD_BRIEF.md section 10.1 step 8).

The review itself is produced by the adversarial reviewer, never by the main
session: through headless ``claude -p --model opus`` when that backend is usable,
otherwise by the ``reviewer`` subagent (.claude/agents/reviewer.md), which writes
``artifacts/review/latest.json`` itself. This script validates that file and prints
it; its last line is the review's final line (``REVIEW: SHIP`` or ``REVIEW: BLOCK``),
or ``REVIEW: MISSING`` / ``REVIEW: INVALID`` when there is nothing valid to print.

``--validate-only`` never launches a model (used by ship-check).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LATEST = REPO / "artifacts" / "review" / "latest.json"
SCHEMA = "graderproof.review/1"
ALLOWED_DIFF_PREFIXES = ("artifacts/review/",)
ALLOWED_DIFF_FILES = ("STATUS.md", "docs/LOG.md")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CATEGORIES = {"gate-false-pass", "wrong-number", "prereg-violation", "section9", "result-defect"}


def git(repo: Path, *args: str) -> tuple[int, str]:
    """Run git in ``repo``; return (exit status, stdout)."""
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def diff_allowed(paths: list[str]) -> list[str]:
    """Paths that a reviewed commit may NOT differ from HEAD in."""
    return [
        p for p in paths if not (p.startswith(ALLOWED_DIFF_PREFIXES) or p in ALLOWED_DIFF_FILES)
    ]


def validate(review: Mapping[str, Any], repo: Path) -> list[str]:
    """Return a list of problems with ``review`` relative to HEAD of ``repo``."""
    problems: list[str] = []
    if review.get("schema") != SCHEMA:
        problems.append(f"schema is {review.get('schema')!r}, expected {SCHEMA}")
    sha = str(review.get("reviewed_commit", ""))
    if not SHA_RE.match(sha):
        problems.append("reviewed_commit is not a full 40-hex sha")
    else:
        rc, _ = git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        if rc != 0:
            problems.append(f"reviewed_commit {sha[:12]} not in history")
        else:
            rc, _ = git(repo, "merge-base", "--is-ancestor", sha, "HEAD")
            if rc != 0:
                problems.append(f"reviewed_commit {sha[:12]} is not an ancestor of HEAD")
            _, names = git(repo, "diff", "--name-only", sha, "HEAD")
            bad = diff_allowed([n for n in names.splitlines() if n])
            if bad:
                problems.append(
                    f"HEAD differs from reviewed commit outside the allowed paths: {bad[:5]}"
                )
    verdict = review.get("verdict")
    blocking = review.get("blocking")
    non_blocking = review.get("non_blocking")
    if verdict not in ("SHIP", "BLOCK"):
        problems.append(f"verdict {verdict!r} is not SHIP or BLOCK")
    if not isinstance(blocking, list) or not isinstance(non_blocking, list):
        problems.append("blocking and non_blocking must be lists")
        return problems
    if verdict == "SHIP" and blocking:
        problems.append("verdict SHIP with open blocking issues")
    if verdict == "BLOCK" and not blocking:
        problems.append("verdict BLOCK with no blocking issues listed")
    for issue in blocking:
        if not isinstance(issue, Mapping):
            problems.append("blocking issue is not an object")
            continue
        for key in ("id", "title", "location", "category", "evidence"):
            if not issue.get(key):
                problems.append(f"blocking issue {issue.get('id', '?')} missing {key}")
        if issue.get("category") not in CATEGORIES:
            problems.append(f"blocking issue {issue.get('id', '?')} has unknown category")
    for issue in non_blocking:
        if not isinstance(issue, Mapping) or not issue.get("id") or not issue.get("title"):
            problems.append("non-blocking issue missing id or title")
    if review.get("final_line") != f"REVIEW: {verdict}":
        problems.append("final_line does not match verdict")
    return problems


def headless_available(env: Mapping[str, str]) -> tuple[bool, str]:
    """Whether headless Claude may be launched for review, and why not."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from doctor import billing_guard_triggers, settings_files

    triggers = billing_guard_triggers(dict(env), settings_files())
    if triggers:
        return False, "billing guard: " + ", ".join(triggers)
    return False, "headless review is wired through the client wrapper once it exists"


def main(argv: list[str]) -> int:
    validate_only = "--validate-only" in argv
    if not validate_only:
        ok, why = headless_available(os.environ)
        if not ok:
            print(f"review: headless Claude not used ({why}).")
            print("review: run the `reviewer` subagent; it writes artifacts/review/latest.json.")
    if not LATEST.exists():
        print("REVIEW: MISSING (no artifacts/review/latest.json yet)")
        return 1
    try:
        review = json.loads(LATEST.read_text())
    except ValueError as exc:
        print(f"REVIEW: INVALID (latest.json is not JSON: {exc})")
        return 1
    problems = validate(review, REPO)
    reviewed = str(review.get("reviewed_commit", "?"))[:12]
    print(f"review of {reviewed} at {review.get('reviewed_at_utc')}")
    for issue in review.get("blocking") or []:
        print(f"  BLOCKING {issue.get('id')}: {issue.get('title')} [{issue.get('location')}]")
    for issue in review.get("non_blocking") or []:
        print(f"  non-blocking {issue.get('id')}: {issue.get('title')}")
    if problems:
        for p in problems:
            print(f"  problem: {p}")
        print("REVIEW: INVALID")
        return 1
    print(review["final_line"])
    return 0 if review["verdict"] == "SHIP" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
