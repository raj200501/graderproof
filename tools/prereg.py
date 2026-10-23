#!/usr/bin/env python3
"""Preregistration chain (`make prereg-verify`, non-negotiable 2).

A preregistration is a file ``prereg/NNNN-<slug>.md``. Freezing it appends an entry to
the append-only chain ``prereg/FROZEN.jsonl``: ``{id, file, sha256, frozen_utc,
git_parent, prev_hash, entry_hash}``, where ``entry_hash`` covers every other field and
``prev_hash`` is the previous entry's hash, so the order of preregistrations is
tamper-evident. The file and its chain entry are then committed together, once.

``verify`` checks, offline:

1. every ``prereg/NNNN-*.md`` has exactly one chain entry and its SHA-256 matches;
2. the chain links (``prev_hash``) and every ``entry_hash`` recomputes;
3. every preregistration file was committed exactly once (never edited after freezing);
4. an amendment (a file whose first lines contain ``Amends: NNNN``) cites an earlier
   preregistration;
5. every confirmatory artifact (``artifacts/**/summary.json`` with ``"confirmatory":
   true``, and ``artifacts/e0/results.json``) cites an existing preregistration whose
   first commit is a proper ancestor of the artifact's first commit.

It fails when there is no preregistration at all (an empty chain proves nothing).
Commands: ``freeze <file>``, ``verify``, ``show``.

Design follows the preregistration chain in raj200501/raise-v1-public (Apache-2.0),
simplified to git ordering without external randomness anchors.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PREREG = REPO / "prereg"
CHAIN = PREREG / "FROZEN.jsonl"
GENESIS = "0" * 64
NAME_RE = re.compile(r"^\d{4}-[a-z0-9][a-z0-9-]*\.md$")
AMENDS_RE = re.compile(r"^\s*Amends:\s*(\d{4})\b", re.I | re.M)


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry_hash(entry: dict[str, Any]) -> str:
    """Hash of an entry's fields other than ``entry_hash``."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def git(repo: Path, *args: str) -> tuple[int, str]:
    """Run git without optional locks."""
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def read_chain(path: Path) -> list[dict[str, Any]]:
    """Chain entries in order (missing file means an empty chain)."""
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def freeze(file: Path, repo: Path = REPO, now: str | None = None) -> dict[str, Any]:
    """Append a chain entry for ``file`` (refuses duplicates and bad names)."""
    prereg_dir, chain_path = repo / "prereg", repo / "prereg" / "FROZEN.jsonl"
    if file.parent.resolve() != prereg_dir.resolve() or not NAME_RE.match(file.name):
        raise ValueError(f"{file} is not prereg/NNNN-<slug>.md")
    chain = read_chain(chain_path)
    if any(e["file"] == file.name for e in chain):
        raise ValueError(f"{file.name} is already frozen")
    _, parent = git(repo, "rev-parse", "HEAD")
    entry: dict[str, Any] = {
        "id": file.name[:4],
        "file": file.name,
        "sha256": sha256_file(file),
        "frozen_utc": now or dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_parent": parent,
        "prev_hash": chain[-1]["entry_hash"] if chain else GENESIS,
    }
    entry["entry_hash"] = entry_hash(entry)
    with chain_path.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def first_commit(repo: Path, rel: str) -> str | None:
    """Commit that first added ``rel``."""
    rc, out = git(repo, "log", "--diff-filter=A", "--format=%H", "--reverse", "--", rel)
    lines = out.splitlines() if rc == 0 and out else []
    return lines[0] if lines else None


def strictly_before(repo: Path, a: str, b: str) -> bool:
    """``a`` is a proper ancestor of ``b``."""
    return a != b and git(repo, "merge-base", "--is-ancestor", a, b)[0] == 0


def confirmatory_artifacts(repo: Path) -> list[Path]:
    """Artifacts that must cite a preregistration."""
    out = []
    art = repo / "artifacts"
    for p in sorted(art.rglob("summary.json")) if art.exists() else []:
        try:
            if json.loads(p.read_text()).get("confirmatory"):
                out.append(p)
        except ValueError:
            out.append(p)
    e0 = art / "e0" / "results.json"
    if e0.exists():
        out.append(e0)
    return out


def verify(repo: Path = REPO) -> list[str]:
    """All problems found (empty means verified)."""
    prereg_dir = repo / "prereg"
    files = (
        sorted(p for p in prereg_dir.glob("*.md") if NAME_RE.match(p.name))
        if prereg_dir.exists()
        else []
    )
    chain = read_chain(prereg_dir / "FROZEN.jsonl")
    problems: list[str] = []
    if not files:
        return ["no preregistrations"]
    prev = GENESIS
    seen: dict[str, dict[str, Any]] = {}
    for i, e in enumerate(chain):
        if e.get("prev_hash") != prev:
            problems.append(f"chain entry {i} does not link to the previous entry")
        if entry_hash(e) != e.get("entry_hash"):
            problems.append(f"chain entry {i} hash does not recompute")
        if e.get("file") in seen:
            problems.append(f"{e.get('file')} frozen twice")
        seen[str(e.get("file"))] = e
        prev = str(e.get("entry_hash"))
    for f in files:
        rel = f.relative_to(repo).as_posix()
        m = AMENDS_RE.search("\n".join(f.read_text().splitlines()[:15]))
        if m and not any(p.name.startswith(m.group(1) + "-") and p.name < f.name for p in files):
            problems.append(f"{rel} amends {m.group(1)}, which is not an earlier preregistration")
        frozen = seen.get(f.name)
        if frozen is None:
            problems.append(f"{rel} has no chain entry (not frozen)")
            continue
        if sha256_file(f) != frozen.get("sha256"):
            problems.append(f"{rel} changed after it was frozen (sha256 mismatch)")
        rc, log = git(repo, "log", "--format=%H", "--", rel)
        n = len(log.splitlines()) if rc == 0 and log else 0
        if n != 1:
            problems.append(f"{rel} has {n} commits (must be committed exactly once)")
    for name in seen:
        if not (prereg_dir / name).exists():
            problems.append(f"chain names {name}, which does not exist")
    for art in confirmatory_artifacts(repo):
        rel = art.relative_to(repo).as_posix()
        try:
            cited = str(json.loads(art.read_text()).get("prereg", ""))
        except ValueError:
            problems.append(f"{rel} is not valid JSON")
            continue
        if not cited.startswith("prereg/") or not (repo / cited).is_file():
            problems.append(f"{rel} cites no existing preregistration")
            continue
        pc, ac = first_commit(repo, cited), first_commit(repo, rel)
        if pc is None or ac is None or not strictly_before(repo, pc, ac):
            problems.append(f"{cited} was not committed before {rel}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "freeze":
        entry = freeze(Path(argv[1]).resolve())
        print(
            f"frozen {entry['file']} sha256 {entry['sha256'][:12]} entry {entry['entry_hash'][:12]}"
        )
        return 0
    if argv == ["show"]:
        for e in read_chain(CHAIN):
            print(f"{e['id']} {e['file']} {e['frozen_utc']} {e['sha256'][:12]}")
        return 0
    if argv in ([], ["verify"]):
        problems = verify(REPO)
        for p in problems:
            print(f"prereg: {p}")
        n = len(read_chain(CHAIN))
        arts = len(confirmatory_artifacts(REPO))
        verdict = "FAIL" if problems else "OK"
        print(f"prereg-verify: {verdict} ({n} frozen, {arts} confirmatory artifacts)")
        return 1 if problems else 0
    print("usage: prereg.py freeze <prereg/NNNN-slug.md> | verify | show", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
