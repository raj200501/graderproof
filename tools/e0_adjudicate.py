#!/usr/bin/env python3
"""E0 adjudication (prereg/0001, DECISIONS.md D23): rule on every flag that is not a detection.

For each counted toybench task that graderproof flagged but did not detect (a flag on
a clean task, or a planted task flagged only in the other direction), every flagged
variant goes to an independent model reviewer through graderproof's client wrapper
(logged, capped, content-addressed; answered by a model-worker subagent, D17). The
reviewer sees the task text, the reference solution, the grader, the flagged variant,
what the grader did with it, and graderproof's witness. It never sees the labels. It
rules only whether the witness validates: whether the variant really breaks (false
accept) or really keeps (false reject) what the task text requires.

A task's flag is adjudicated real when at least one of its flagged variants validates.
The rulings and reasons are written to ``artifacts/e0/adjudication.json``, which exists
even when no flag needs a ruling. The build session does not overrule them.

The provenance block keeps the keys every graderproof artifact carries. They describe the
checkout the tool runs in and the package it imports (``git_sha``, ``git_dirty``,
``package_fingerprint``), which for E0 are the frozen worktree's. The tool file itself can
come from another checkout, so its own source, read as the run starts, is recorded beside
them: ``tool_git_sha`` (HEAD of the checkout that holds the tool file), ``tool_git_dirty``
(false only when the tool file is exactly its blob at that commit, with no uncommitted
change), and ``tool_sha256`` (the SHA-256 of the tool file). When ``tool_git_dirty`` is
false, ``git cat-file blob <tool_git_sha>:tools/e0_adjudicate.py`` hashes to
``tool_sha256``. An adjudication written before these keys existed does not have them
(review of 5677b9f, N2).

Usage (from the frozen E0 worktree, after the audit is complete)::

    python3 <main>/tools/e0_adjudicate.py --audit artifacts/e0 --labels toybench/labels.json \
        --tasks toybench/tasks --store artifacts/model_calls/e0 \
        --ledger <main>/artifacts/usage/ledger.jsonl --out artifacts/e0/adjudication.json

Exit status 0 when the file is written, 3 when model requests are pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TOOL_FILE = Path(__file__).resolve()
# Variables that point git at another repository, work tree, index, or object store (git
# sets some of them for hooks, for example); dropped so the tool's own checkout is read.
GIT_REPO_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
)
PURPOSE = "adjudicate"
PROMPT_VERSION = "adjudicate/v1"
PENDING = 3
INSTRUCTIONS = """\
You are an independent adjudicator for an audit of benchmark graders. Each item is one
modified solution of one task. It gives the task text (the instructions a solver gets),
the reference solution, the grader's source, the modified solution (as a diff and as full
files), what the grader did with the modified solution, and the auditing tool's witness:
the requirement(s) of the task text that the tool says the modified solution breaks (for
a "false accept" item) or keeps (for a "false reject" item).

Decide only whether the tool's claim is correct, judging from the task text as written,
not from what the grader happens to check:
- "false accept" item: the grader ACCEPTED the modified solution. Answer "validates" if
  the modified solution really fails to do what the task text requires (the witness's
  requirement, or another requirement the task text states explicitly), so that a careful
  reader of the task text would reject it. Answer "does-not-validate" if the modified
  solution is acceptable under the task text (for example, the named requirement is not
  actually stated, or the change does not break it).
- "false reject" item: the grader REJECTED the modified solution. Answer "validates" if
  the modified solution satisfies everything the task text requires, so the rejection is
  not justified by the task text. Answer "does-not-validate" if the task text does require
  something the modified solution does not do.
Give a reason of one or two sentences that names the requirement you relied on.
"""
SCHEMA: dict[str, Any] = {
    "required": ["verdict", "reason"],
    "enums": {"verdict": ["validates", "does-not-validate"]},
}


def read_tree(root: Path) -> dict[str, str]:
    """Text files under ``root`` by relative path (empty if missing)."""
    if not root.is_dir():
        return {}
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return out


def flagged_variants(
    evidence: Mapping[str, Any], flags: Mapping[str, bool]
) -> list[dict[str, Any]]:
    """The counted variants behind a task's false-accept and false-reject flags."""
    out = []
    for v in evidence.get("variants", []):
        if not v.get("counted_in_headline"):
            continue
        if flags.get("false_accept") and v.get("kind") == "violating" and v.get("grader_passed"):
            out.append({**v, "flag": "false accept"})
        elif (
            flags.get("false_reject")
            and v.get("kind") == "preserving"
            and not v.get("grader_passed", True)
        ):
            out.append({**v, "flag": "false reject"})
    return out


def witness_text(witness: Mapping[str, Any] | None, requirements: Mapping[str, str]) -> Any:
    """The witness with each requirement id expanded to its text."""
    if not witness:
        return None
    out: dict[str, Any] = {}
    for key in ("broken", "held"):
        entries = witness.get(key) or []
        rows = []
        for e in entries:
            rid = e.get("requirement") if isinstance(e, Mapping) else e
            row = dict(e) if isinstance(e, Mapping) else {"requirement": rid}
            row["requirement_text"] = requirements.get(str(rid), "")
            rows.append(row)
        if rows:
            out[key] = rows
    return out


def build_items(
    needs: Sequence[str],
    rows: Mapping[str, Mapping[str, Any]],
    evidence_dir: Path,
    tasks_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Model items for every flagged variant of the tasks in ``needs``, and their owners."""
    items: list[dict[str, Any]] = []
    owners: dict[str, list[str]] = {}
    for tid in needs:
        row = rows[tid]
        evidence = json.loads((evidence_dir / f"{row['task_hash']}.json").read_text())
        reqs = {str(r["id"]): str(r.get("text", "")) for r in evidence.get("requirements", [])}
        task_dir = tasks_dir / tid
        task_text = (task_dir / "instruction.md").read_text(encoding="utf-8", errors="replace")
        flags = {k: bool(row.get(k)) for k in ("false_accept", "false_reject")}
        owners[tid] = []
        for v in flagged_variants(evidence, flags):
            owners[tid].append(str(v["id"]))
            items.append(
                {
                    "id": str(v["id"]),
                    "flag": v["flag"],
                    "task_text": task_text,
                    "reference_solution": read_tree(task_dir / "solution"),
                    "grader_files": read_tree(task_dir / "grader"),
                    "modified_diff": v.get("diff", ""),
                    "modified_files": v.get("files", {}),
                    "witness": witness_text(v.get("witness"), reqs),
                }
            )
    return items, owners


def rulings(
    owners: Mapping[str, Sequence[str]], answers: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Per-task rulings: real when at least one flagged variant validates."""
    out: dict[str, dict[str, Any]] = {}
    for tid, vids in sorted(owners.items()):
        per = [
            {"variant_id": vid, **{k: answers[vid][k] for k in ("verdict", "reason")}}
            for vid in vids
        ]
        real = any(p["verdict"] == "validates" for p in per)
        reason = next((p["reason"] for p in per if p["verdict"] == "validates"), "")
        if not reason:
            reason = per[0]["reason"] if per else "no counted flagged variant in the evidence"
        out[tid] = {"real": real, "reason": reason, "variants": per}
    return out


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run git on the checkout that contains ``cwd``, as that checkout really is.

    The variables in ``GIT_REPO_ENV`` are dropped, replacement refs (which can make another
    commit stand in for HEAD) are not used, and no optional lock is taken, so ``git status``
    never rewrites the index of a checkout that others are working in.
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_REPO_ENV}
    return subprocess.run(
        ["git", "--no-optional-locks", "--no-replace-objects", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )


def tool_provenance(path: Path) -> dict[str, str | bool]:
    """The source of the tool file at ``path``, whichever checkout the tool runs in.

    ``tool_sha256`` is the SHA-256 of the file's bytes, read once. ``tool_git_sha`` is HEAD
    of the checkout that holds the file (``unknown`` outside git). ``tool_git_dirty`` is
    false only when those bytes are the file's blob at that very commit and ``git status``
    reports no change to the file, staged or not. So a clean record can be checked offline:
    ``git cat-file blob <tool_git_sha>:<path>`` hashes to ``tool_sha256``. A file that is
    untracked or ignored, flagged assume-unchanged or skip-worktree, changed by a commit
    made while this runs, or in no readable checkout is dirty.
    """
    tool = path.resolve()
    data = tool.read_bytes()  # the bytes hashed are the bytes compared
    head = _git(tool.parent, "rev-parse", "HEAD")
    sha = head.stdout.decode().strip() if head.returncode == 0 else "unknown"
    clean = False
    if head.returncode == 0:
        # The blob at the commit recorded here, not at wherever HEAD has moved since.
        blob = _git(tool.parent, "cat-file", "blob", f"{sha}:./{tool.name}")
        # What the blob cannot show: a staged change undone on disk, or removal from the index.
        status = _git(tool.parent, "status", "--porcelain", "--", tool.name)
        clean = (
            blob.returncode == 0
            and blob.stdout == data
            and status.returncode == 0
            and not status.stdout.strip()
        )
    return {
        "tool_git_sha": sha,
        "tool_git_dirty": not clean,
        "tool_sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    # Before any input is read or model call made, so the record describes the tool file as
    # this run loaded it, whatever is edited or reverted while the run goes on.
    tool_source = tool_provenance(TOOL_FILE)
    try:  # the package of the environment it runs in (the frozen worktree's, for E0)
        import graderproof  # noqa: F401
    except ImportError:  # pragma: no cover - only outside an environment with the package
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from graderproof import e0
    from graderproof.audit import AuditConfig, provenance
    from graderproof.models import ModelClient, PendingWorkError

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audit", type=Path, default=Path("artifacts/e0"))
    ap.add_argument("--labels", type=Path, default=Path("toybench/labels.json"))
    ap.add_argument("--tasks", type=Path, default=Path("toybench/tasks"))
    ap.add_argument("--store", type=Path, default=Path("artifacts/model_calls/e0"))
    ap.add_argument("--ledger", type=Path, default=Path("artifacts/usage/ledger.jsonl"))
    ap.add_argument("--budget", type=Path, default=Path("budget.toml"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/e0/adjudication.json"))
    ap.add_argument("--prereg", default="prereg/0001-e0-tool-validity.md")
    ap.add_argument("--batch", type=int, default=10)
    args = ap.parse_args(argv)

    labels = json.loads(args.labels.read_text())["tasks"]
    audit_rows = [
        json.loads(line) for line in (args.audit / "tasks.jsonl").read_text().splitlines()
    ]
    scores = e0.task_scores(audit_rows, labels, {})
    needs = sorted(s.task for s in e0.needs_adjudication(scores) if s.slice != "extra")
    rows = {str(r["task"]).split(":", 1)[-1]: r for r in audit_rows}
    items, owners = build_items(needs, rows, args.audit / "evidence", args.tasks)
    client = ModelClient(store=args.store, ledger=args.ledger, budget=args.budget)
    answers: dict[str, dict[str, Any]] = {}
    if items:
        try:
            answers = client.batch_items(
                PURPOSE, PROMPT_VERSION, INSTRUCTIONS, SCHEMA, items, args.batch
            )
        except PendingWorkError as exc:
            for h in exc.hashes:
                print(f"pending {args.store / 'requests' / (h + '.json')}")
            print(f"e0-adjudicate: {len(exc.hashes)} model requests pending", file=sys.stderr)
            return PENDING
    doc = {
        "schema": "graderproof.e0_adjudication/1",
        "prereg": args.prereg,
        "prompt_version": PROMPT_VERSION,
        "rule": "real when at least one flagged variant's witness validates (D23)",
        "tasks": rulings(owners, answers),
        "models": client.served_models(),
        "provenance": provenance(AuditConfig(), {"tool": "tools/e0_adjudicate.py", **tool_source}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"e0-adjudicate: {len(owners)} tasks ruled, {len(items)} variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
