#!/usr/bin/env python3
"""Secrets scan (`make secrets-scan`, non-negotiable 6).

Scans every tracked file and every blob in git history for:

* well-known credential formats (cloud keys, GitHub, Anthropic, OpenAI, Google,
  OpenRouter, Slack tokens, private key blocks);
* the literal value of any secret-looking environment variable currently set
  (names containing KEY, TOKEN, SECRET, PASSWORD, or CREDENTIAL);
* tracked ``.env`` files.

It prints only file names, line numbers, and pattern or variable names, never a
matched value. Exit status 1 on any finding.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PATTERNS: dict[str, re.Pattern[str]] = {
    "aws-access-key-id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "github-fine-grained-pat": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    "anthropic-key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "openrouter-key": re.compile(r"\bsk-or-v1-[a-f0-9]{40,}\b"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "private-key-block": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
}
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
# Names that match SECRET_NAME but hold configuration, not secrets.
NOT_SECRET_NAME = re.compile(r"^GIT_CONFIG_KEY_\d+$|_(?:FILE|PATH|DIR)$")
MIN_SECRET_LEN = 16


def secret_env_values(env: Mapping[str, str]) -> dict[str, str]:
    """Secret-looking environment variables with values long enough to search for."""
    return {
        k: v
        for k, v in env.items()
        if SECRET_NAME.search(k)
        and not NOT_SECRET_NAME.search(k)
        and len(v) >= MIN_SECRET_LEN
        and not v.startswith("/")
    }


def scan_text(label: str, text: str, env_secrets: Mapping[str, str]) -> list[str]:
    """Findings for one text blob, as ``label:line kind`` strings."""
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pat in PATTERNS.items():
            if pat.search(line):
                findings.append(f"{label}:{lineno} {name}")
        for var, value in env_secrets.items():
            if value in line:
                findings.append(f"{label}:{lineno} value-of-${var}")
    return findings


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def tracked(repo: Path) -> list[str]:
    """Tracked paths."""
    return [p for p in _git(repo, "ls-files", "-z").decode().split("\0") if p]


def history_blobs(repo: Path) -> list[tuple[str, str]]:
    """(blob sha, a path it appeared at) for every blob reachable from any ref."""
    out = _git(repo, "rev-list", "--all", "--objects").decode()
    candidates: dict[str, str] = {}
    for line in out.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            candidates.setdefault(sha, path)
    if not candidates:
        return []
    check = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="\n".join(candidates).encode(),
        capture_output=True,
        check=True,
    ).stdout.decode()
    blobs = [ln.split()[0] for ln in check.splitlines() if ln.endswith(" blob")]
    return [(b, candidates[b]) for b in blobs]


def read_blob(repo: Path, sha: str) -> bytes:
    """Raw content of one blob."""
    return _git(repo, "cat-file", "blob", sha)


def decode(data: bytes) -> str | None:
    """UTF-8 text, or None for binary data."""
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def scan(repo: Path, env: Mapping[str, str], history: bool = True) -> list[str]:
    """All findings for the repository."""
    env_secrets = secret_env_values(env)
    findings: list[str] = []
    paths = tracked(repo)
    for rel in paths:
        name = rel.rsplit("/", 1)[-1]
        if name == ".env" or name.startswith(".env."):
            findings.append(f"{rel}:0 tracked-env-file")
        try:
            text = decode((repo / rel).read_bytes())
        except OSError:
            continue
        if text is not None:
            findings += scan_text(rel, text, env_secrets)
    if history:
        seen_now = set(findings)
        for sha, path in history_blobs(repo):
            text = decode(read_blob(repo, sha))
            if text is None:
                continue
            for f in scan_text(f"history:{sha[:12]}:{path}", text, env_secrets):
                if f not in seen_now:
                    findings.append(f)
    return dedupe(findings)


def dedupe(items: Iterable[str]) -> list[str]:
    """Order-preserving de-duplication."""
    return list(dict.fromkeys(items))


def main(argv: list[str]) -> int:
    history = "--no-history" not in argv
    findings = scan(REPO, os.environ, history=history)
    for f in findings:
        print(f"secret: {f}")
    if findings:
        print(f"secrets-scan: FAIL ({len(findings)} findings)")
        return 1
    print(f"secrets-scan: clean ({len(tracked(REPO))} tracked files, history={history})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
