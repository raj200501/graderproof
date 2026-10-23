"""Task requirements and machine-checkable checks, evaluated on solution outcomes.

Requirements are derived from the task text (never from the grader). Each requirement
holds one or more typed checks; a requirement holds on an outcome when all of its
checks pass. Checks are evaluated in-process on data already collected from the
sandbox (workspace files, process output, trajectory, final state, and the results of
sandboxed function-call probes), so no untrusted code runs here.

Check types (``{"type": ..., ...}``):

* ``file_exists`` / ``file_absent``: ``path``
* ``file_equals``: ``path``, ``text``, optional ``normalize`` (``none``, ``strip``,
  ``trailing_ws``)
* ``file_contains``: ``path``, ``text``; ``file_regex``: ``path``, ``pattern``
* ``file_json``: ``path``, ``pointer`` (RFC 6901), ``equals``, optional ``lenient``
* ``file_lines``: ``path``, ``count`` (non-empty lines)
* ``stdout_contains``: ``text``; ``stdout_regex``: ``pattern``;
  ``stdout_json``: ``pointer``, ``equals``, optional ``lenient``
* ``exit_code``: ``code``
* ``call``: ``probe`` (``function``, ``args``, ``kwargs``), and ``equals`` or
  ``matches_reference: true`` (differential against the reference outcome)
* ``same_as_reference``: ``target`` (``stdout``, ``state``, or ``file:<path>``),
  optional ``normalize``
* ``trajectory_includes`` / ``trajectory_excludes``: ``tool``, optional ``args`` subset
* ``trajectory_before``: ``first`` and ``then`` (each ``{tool, args?}``)
* ``state_equals``: ``pointer``, ``equals``

``lenient`` JSON parsing strips surrounding whitespace and one Markdown code fence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from graderproof.core import canonical_json, sha256_text

FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_-]*\s*\n(.*?)\n\s*```\s*$", re.S)
CHECK_TYPES = frozenset(
    {
        "file_exists",
        "file_absent",
        "file_equals",
        "file_contains",
        "file_regex",
        "file_json",
        "file_lines",
        "stdout_contains",
        "stdout_regex",
        "stdout_json",
        "exit_code",
        "call",
        "same_as_reference",
        "trajectory_includes",
        "trajectory_excludes",
        "trajectory_before",
        "state_equals",
    }
)


@dataclass(frozen=True)
class Outcome:
    """What one execution of a solution produced, as seen by checks.

    Attributes:
        files: Workspace text files after the solution ran, relative path to content.
        stdout: Solution standard output.
        stderr: Solution standard error.
        exit_status: Solution exit status.
        timed_out: Whether the solution hit its time limit.
        trajectory: Tool calls executed, ``{"tool", "args", "result"|"error"}``.
        state: Final environment state for stateful tool-use tasks.
        probes: Results of sandboxed function-call probes, keyed by :func:`probe_key`.
    """

    files: Mapping[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_status: int = 0
    timed_out: bool = False
    trajectory: Sequence[Mapping[str, Any]] = ()
    state: Mapping[str, Any] | None = None
    probes: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "files": dict(self.files),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_status": self.exit_status,
            "timed_out": self.timed_out,
            "trajectory": [dict(t) for t in self.trajectory],
            "state": None if self.state is None else dict(self.state),
            "probes": {k: dict(v) for k, v in self.probes.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Outcome:
        """Inverse of :meth:`to_dict`."""
        state = data.get("state")
        return cls(
            files=dict(data.get("files", {})),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            exit_status=int(data.get("exit_status", 0)),
            timed_out=bool(data.get("timed_out", False)),
            trajectory=tuple(data.get("trajectory", ())),
            state=None if state is None else dict(state),
            probes=dict(data.get("probes", {})),
        )


@dataclass(frozen=True)
class CheckResult:
    """Whether one check passed, with a short human-readable detail."""

    passed: bool
    detail: str


@dataclass(frozen=True)
class Requirement:
    """One atomic requirement from the task text with its machine-checkable checks."""

    id: str
    text: str
    checks: tuple[Mapping[str, Any], ...]
    source: str = ""

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError(f"requirement {self.id} has no checks")
        for c in self.checks:
            if c.get("type") not in CHECK_TYPES:
                raise ValueError(f"requirement {self.id}: unknown check type {c.get('type')!r}")

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON representation."""
        return {
            "id": self.id,
            "text": self.text,
            "checks": [dict(c) for c in self.checks],
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Requirement:
        """Inverse of :meth:`to_dict`."""
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            checks=tuple(dict(c) for c in data["checks"]),
            source=str(data.get("source", "")),
        )


def probe_key(probe: Mapping[str, Any]) -> str:
    """Stable key for a function-call probe."""
    return sha256_text(canonical_json(dict(probe)))[:16]


def probes_of(requirements: Sequence[Requirement]) -> list[dict[str, Any]]:
    """Every distinct function-call probe the requirements need, in first-use order."""
    seen: dict[str, dict[str, Any]] = {}
    for req in requirements:
        for check in req.checks:
            if check.get("type") == "call":
                probe = dict(check["probe"])
                seen.setdefault(probe_key(probe), probe)
    return list(seen.values())


def json_pointer(doc: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON pointer; raises KeyError when it does not resolve."""
    if pointer in ("", "/"):
        return doc
    cur = doc
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(pointer) from exc
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(pointer)
            cur = cur[part]
        else:
            raise KeyError(pointer)
    return cur


def parse_json(text: str, lenient: bool) -> Any:
    """Parse JSON; with ``lenient`` also accept one surrounding Markdown code fence."""
    if lenient:
        m = FENCE_RE.match(text)
        if m:
            text = m.group(1)
    return json.loads(text)


def normalize(text: str, mode: str) -> str:
    """Apply a text normalization mode."""
    if mode == "strip":
        return text.strip()
    if mode == "trailing_ws":
        return "\n".join(line.rstrip() for line in text.rstrip("\n").split("\n"))
    return text


def _call_matches(call: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    if call.get("tool") != spec.get("tool"):
        return False
    args = call.get("args") or {}
    want = spec.get("args") or {}
    return all(args.get(k) == v for k, v in want.items())


def _first_index(traj: Sequence[Mapping[str, Any]], spec: Mapping[str, Any]) -> int | None:
    for i, call in enumerate(traj):
        if _call_matches(call, spec):
            return i
    return None


def _target(outcome: Outcome, target: str) -> Any:
    if target == "stdout":
        return outcome.stdout
    if target == "state":
        return outcome.state
    if target.startswith("file:"):
        return outcome.files.get(target[5:])
    raise ValueError(f"unknown same_as_reference target {target!r}")


def evaluate(
    check: Mapping[str, Any], outcome: Outcome, reference: Outcome | None = None
) -> CheckResult:
    """Evaluate one check on an outcome (``reference`` is needed by differential checks)."""
    t = check.get("type")
    path = str(check.get("path", ""))
    content = outcome.files.get(path)
    if t == "file_exists":
        return CheckResult(
            content is not None, f"{path} {'exists' if content is not None else 'missing'}"
        )
    if t == "file_absent":
        return CheckResult(content is None, f"{path} {'absent' if content is None else 'present'}")
    if t in ("file_equals", "file_contains", "file_regex", "file_json", "file_lines"):
        if content is None:
            return CheckResult(False, f"{path} missing")
        return _evaluate_text(check, content, path)
    if t == "stdout_contains":
        ok = str(check["text"]) in outcome.stdout
        return CheckResult(ok, f"stdout {'contains' if ok else 'lacks'} {check['text']!r}")
    if t == "stdout_regex":
        ok = re.search(str(check["pattern"]), outcome.stdout, re.M) is not None
        return CheckResult(
            ok, f"stdout {'matches' if ok else 'does not match'} /{check['pattern']}/"
        )
    if t == "stdout_json":
        return _evaluate_json(check, outcome.stdout, "stdout")
    if t == "exit_code":
        ok = outcome.exit_status == int(check["code"]) and not outcome.timed_out
        return CheckResult(
            ok, f"exit {outcome.exit_status}{' (timeout)' if outcome.timed_out else ''}"
        )
    if t == "call":
        return _evaluate_call(check, outcome, reference)
    if t == "same_as_reference":
        if reference is None:
            raise ValueError("same_as_reference needs the reference outcome")
        mode = str(check.get("normalize", "none"))
        mine, theirs = (
            _target(outcome, str(check["target"])),
            _target(reference, str(check["target"])),
        )
        if isinstance(mine, str) and isinstance(theirs, str):
            mine, theirs = normalize(mine, mode), normalize(theirs, mode)
        ok = mine == theirs and mine is not None
        return CheckResult(ok, f"{check['target']} {'equals' if ok else 'differs from'} reference")
    if t == "trajectory_includes":
        ok = _first_index(outcome.trajectory, check) is not None
        return CheckResult(ok, f"trajectory {'has' if ok else 'lacks'} {check.get('tool')}")
    if t == "trajectory_excludes":
        ok = _first_index(outcome.trajectory, check) is None
        return CheckResult(ok, f"trajectory {'avoids' if ok else 'has'} {check.get('tool')}")
    if t == "trajectory_before":
        a = _first_index(outcome.trajectory, check["first"])
        b = _first_index(outcome.trajectory, check["then"])
        ok = a is not None and b is not None and a < b
        return CheckResult(
            ok, f"order {check['first'].get('tool')} < {check['then'].get('tool')}: {a}, {b}"
        )
    if t == "state_equals":
        try:
            got = json_pointer(outcome.state, str(check["pointer"]))
        except KeyError:
            return CheckResult(False, f"state {check['pointer']} missing")
        ok = got == check["equals"]
        return CheckResult(ok, f"state {check['pointer']} = {got!r}")
    raise ValueError(f"unknown check type {t!r}")


def _evaluate_text(check: Mapping[str, Any], content: str, path: str) -> CheckResult:
    t = check["type"]
    if t == "file_equals":
        mode = str(check.get("normalize", "none"))
        ok = normalize(content, mode) == normalize(str(check["text"]), mode)
        return CheckResult(ok, f"{path} {'equals' if ok else 'differs from'} expected text")
    if t == "file_contains":
        ok = str(check["text"]) in content
        return CheckResult(ok, f"{path} {'contains' if ok else 'lacks'} {check['text']!r}")
    if t == "file_regex":
        ok = re.search(str(check["pattern"]), content, re.M) is not None
        return CheckResult(
            ok, f"{path} {'matches' if ok else 'does not match'} /{check['pattern']}/"
        )
    if t == "file_lines":
        n = sum(1 for line in content.splitlines() if line.strip())
        ok = n == int(check["count"])
        return CheckResult(ok, f"{path} has {n} non-empty lines")
    return _evaluate_json(check, content, path)


def _evaluate_json(check: Mapping[str, Any], text: str, where: str) -> CheckResult:
    try:
        doc = parse_json(text, bool(check.get("lenient", False)))
    except ValueError:
        return CheckResult(False, f"{where} is not valid JSON")
    try:
        got = json_pointer(doc, str(check.get("pointer", "")))
    except KeyError:
        return CheckResult(False, f"{where} {check.get('pointer')} missing")
    ok = got == check["equals"]
    return CheckResult(ok, f"{where} {check.get('pointer')} = {got!r}")


def _evaluate_call(
    check: Mapping[str, Any], outcome: Outcome, reference: Outcome | None
) -> CheckResult:
    key = probe_key(check["probe"])
    got = outcome.probes.get(key)
    name = check["probe"].get("function")
    if got is None:
        return CheckResult(False, f"probe {name} not run")
    if check.get("matches_reference"):
        if reference is None:
            raise ValueError("matches_reference needs the reference outcome")
        want = reference.probes.get(key)
        if want is None or not want.get("ok"):
            return CheckResult(False, f"reference probe {name} unavailable")
        ok = bool(got.get("ok")) and got.get("value") == want.get("value")
        return CheckResult(ok, f"{name} {'matches' if ok else 'differs from'} reference")
    ok = bool(got.get("ok")) and got.get("value") == check.get("equals")
    return CheckResult(ok, f"{name} returned {got.get('value')!r}")


def holds(
    req: Requirement, outcome: Outcome, reference: Outcome | None = None
) -> tuple[bool, list[CheckResult]]:
    """Whether every check of ``req`` passes on ``outcome``."""
    results = [evaluate(c, outcome, reference) for c in req.checks]
    return all(r.passed for r in results), results


def load_requirements(data: Mapping[str, Any]) -> list[Requirement]:
    """Requirements from a ``{"requirements": [...]}`` document."""
    return [Requirement.from_dict(r) for r in data.get("requirements", [])]
