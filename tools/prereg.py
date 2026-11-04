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
5. every confirmatory artifact cites a frozen preregistration whose commit predates
   the artifact's data. Confirmatory artifacts are every ``artifacts/**/summary.json``
   with ``"confirmatory": true``, ``artifacts/e0/summary.json`` (which must say
   ``"confirmatory": true``), and ``artifacts/e0/results.json``. The citation is the
   ``"prereg"`` field, a path ``prereg/NNNN-<slug>.md``. The artifact's data are the
   files under its own directory, under the directory named by its ``"model_store"``
   field (a path under ``artifacts/``), and for E0 under ``artifacts/model_calls/e0/``.
   The preregistration's commit must be a proper ancestor of every commit that added
   a file there anywhere in the history (merges included) and of every commit that
   added a file later renamed into them (true renames at 90% similarity or more;
   copies are not followed). So E0 outputs or model calls committed before the E0
   preregistration fail, whatever order the later files arrive in.

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
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PREREG = REPO / "prereg"
CHAIN = PREREG / "FROZEN.jsonl"
GENESIS = "0" * 64
NAME_RE = re.compile(r"^\d{4}-[a-z0-9][a-z0-9-]*\.md$")
CITE_RE = re.compile(r"^prereg/\d{4}-[a-z0-9][a-z0-9-]*\.md$")
AMENDS_RE = re.compile(r"^\s*Amends:\s*(\d{4})\b", re.I | re.M)
E0_DIR = "artifacts/e0"
E0_SUMMARY = "artifacts/e0/summary.json"
E0_RESULTS = "artifacts/e0/results.json"
E0_MODEL_STORE = "artifacts/model_calls/e0"


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


def commits_of(repo: Path, rel: str) -> list[str]:
    """Commits that changed ``rel``, newest first (git's default history simplification,
    so a branch merged without changes of its own is not a second commit)."""
    rc, out = git(repo, "log", "--format=%H", "--", rel)
    return out.splitlines() if rc == 0 and out else []


def strictly_before(repo: Path, a: str, b: str) -> bool:
    """``a`` is a proper ancestor of ``b``."""
    return a != b and git(repo, "merge-base", "--is-ancestor", a, b)[0] == 0


def adds(repo: Path, paths: Sequence[str]) -> list[str]:
    """Commits that add a file under ``paths`` anywhere in the history (merges included)."""
    rc, out = git(
        repo, "log", "--full-history", "-m", "--diff-filter=A", "--format=%H", "--", *paths
    )
    return out.splitlines() if rc == 0 and out else []


def renames(repo: Path) -> list[tuple[str, str]]:
    """(source, destination) of every true rename in the history (90% similar or more).

    Copies are not followed: ``git log --follow`` would date new data by any older
    file that happens to look like it.
    """
    rc, out = git(
        repo, "log", "--full-history", "-m", "-M90%", "--diff-filter=R", "--name-status",
        "--format=",
    )  # fmt: skip
    parts = [ln.split("\t") for ln in out.splitlines()] if rc == 0 else []
    return [(p[1], p[2]) for p in parts if len(p) == 3 and p[0].startswith("R")]


def data_commits(repo: Path, dirs: Sequence[str]) -> list[str]:
    """Every commit that brought a file into ``dirs``: adds anywhere in the history
    (merges included) and the adds of any file later renamed into them (chains followed)."""

    def under(path: str) -> bool:
        return any(path == d or path.startswith(d.rstrip("/") + "/") for d in dirs)

    found = adds(repo, dirs)
    moves = renames(repo)
    todo = {src for src, dst in moves if under(dst)}
    seen: set[str] = set()
    while todo:
        src = todo.pop()
        if src not in seen:
            seen.add(src)
            found += adds(repo, [src])
            todo |= {s for s, d in moves if d == src}
    return list(dict.fromkeys(found))


def data_dirs(rel: str, doc: dict[str, Any]) -> tuple[list[str], str]:
    """(directories whose files date the artifact at ``rel``, problem or empty)."""
    where = PurePosixPath(rel).parent.as_posix()
    dirs = [where]
    store = doc.get("model_store")
    if store not in (None, ""):
        value = str(store).rstrip("/")
        p = PurePosixPath(value)
        if (
            not isinstance(store, str)
            or p.is_absolute()
            or ".." in p.parts
            or p.as_posix() != value
            or not value.startswith("artifacts/")
        ):
            return [], f"{rel}: model_store {store!r} is not a directory under artifacts/"
        dirs.append(value)
    if where == E0_DIR or where.startswith(E0_DIR + "/"):
        dirs.append(E0_MODEL_STORE)
    return list(dict.fromkeys(dirs)), ""


def confirmatory_artifacts(repo: Path) -> list[Path]:
    """Artifacts that must cite a preregistration (unreadable summaries included)."""
    out = []
    art = repo / "artifacts"
    for p in sorted(art.rglob("summary.json")) if art.exists() else []:
        try:
            doc = json.loads(p.read_text())
        except ValueError:
            out.append(p)
            continue
        if (
            not isinstance(doc, dict)
            or p.relative_to(repo).as_posix() == E0_SUMMARY
            or doc.get("confirmatory")
        ):
            out.append(p)
    e0 = repo / E0_RESULTS
    if e0.exists():
        out.append(e0)
    return out


def artifact_problems(repo: Path, art: Path, frozen: set[str]) -> list[str]:
    """Why one confirmatory artifact is not preceded by its preregistration (or [])."""
    rel = art.relative_to(repo).as_posix()
    try:
        doc = json.loads(art.read_text())
    except ValueError:
        return [f"{rel} is not valid JSON"]
    if not isinstance(doc, dict):
        return [f"{rel} is not a JSON object"]
    problems = []
    if rel == E0_SUMMARY and doc.get("confirmatory") is not True:
        problems.append(f"{rel} is not marked confirmatory")
    cited = doc.get("prereg")
    if not isinstance(cited, str) or not CITE_RE.match(cited) or not (repo / cited).is_file():
        return [*problems, f"{rel} cites no existing preregistration"]
    if PurePosixPath(cited).name not in frozen:
        return [*problems, f"{rel} cites {cited}, which is not frozen"]
    commits = commits_of(repo, cited)
    if len(commits) != 1:
        return [*problems, f"{rel} cites {cited}, which is not committed exactly once"]
    dirs, why = data_dirs(rel, doc)
    if why:
        return [*problems, why]
    data = data_commits(repo, dirs)
    if not data:
        return [*problems, f"{cited} was not committed before {rel} (nothing under {dirs})"]
    bad = next((c for c in data if not strictly_before(repo, commits[0], c)), None)
    if bad:
        problems.append(
            f"{cited} was not committed before {rel} (commit {bad[:12]} adds files under "
            f"{', '.join(dirs)})"
        )
    return problems


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
        n = len(commits_of(repo, rel))
        if n != 1:
            problems.append(f"{rel} has {n} commits (must be committed exactly once)")
    for name in seen:
        if not (prereg_dir / name).exists():
            problems.append(f"chain names {name}, which does not exist")
    for art in confirmatory_artifacts(repo):
        problems += artifact_problems(repo, art, set(seen))
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
