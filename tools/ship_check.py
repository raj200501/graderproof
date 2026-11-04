#!/usr/bin/env python3
"""graderproof ship-check: the 14 Definition-of-Done gates of docs/BUILD_BRIEF.md section 6.

Procedure (docs/BUILD_BRIEF.md section 10.1 step 9):

1. In the original checkout, check the parts of G14 about the working tree and
   ``private/``, and verify private hash manifests (``outbound/patches/MANIFEST.json``)
   against the files under ``private/``. Of a private JSON file only its ``accepted``
   and ``task_hash`` fields are read (for G8); nothing private is printed.
2. Make a fresh clone of HEAD in a temporary directory and run every other check there.
   Banked artifacts are verified (presence, provenance, hashes, preregistration links,
   thresholds) and statistics are recomputed from them. No experiment is run and no
   model is called. Nothing is written inside the working tree; sub-command logs go to
   the temporary directory.

Stdout is exactly ``HEAD <sha> fresh-clone``, one ``G<n> <PASS|FAIL> <evidence>`` line
per gate, then ``SHIP-CHECK: PASS 14/14`` or ``SHIP-CHECK: FAIL <passed>/14``. With
``--fast`` the slow ``make ci`` reruns are skipped (G3 is derived from the G1, G2, and
G4 steps instead) and the last line is ``SHIP-CHECK-FAST (does not count): <passed>/14``.

A gate whose property ranges over a set (preregistrations, confirmatory artifacts,
headline variants, surviving variants, repaired tasks, references, benchmarks) fails
when the set is empty: an empty set proves nothing (DECISIONS.md D6).

Rules shared by every gate:

* Flags are JSON booleans: ``"true"``, ``1``, and ``null`` never count as true.
  Statistics are JSON numbers, never booleans.
* A bootstrap block is ``{"seed": int, "B": int >= 1000, "alpha": 0.05}`` (95% intervals).
* A task is **scorable** when its tasks.jsonl row has ``determinism == "stable_pass"``
  (D26). A variant is **counted** when ``counted_in_headline`` is true and
  ``grader_passed`` is exactly true or false. A scorable task has a **false accept**
  when a counted violating variant has ``grader_passed: true`` (a **surviving**
  variant), and a **false reject** when a counted preserving variant has
  ``grader_passed: false``. Tasks that are not scorable have neither.
* A commit **predates** a set of directories when it is a proper ancestor of every
  commit that added a file under them anywhere in the history (merges included) and
  of every commit that added a file later renamed into them (true renames at 90%
  similarity or more; copies are not followed).
* A preregistration citation is a path ``prereg/NNNN-<slug>.md`` of a file that is
  committed exactly once and frozen in ``prereg/FROZEN.jsonl`` with its SHA-256.

Artifact contracts (later iterations may tighten them, never loosen):

* Audit tables, in ``artifacts/audit/<benchmark>/`` and ``artifacts/e0/``:
  ``tasks.jsonl`` has one row per task with ``task_hash`` (64 hex, unique) and
  ``determinism`` (``stable_pass``, ``stable_fail``, or ``flaky``). Its flags
  ``false_accept``, ``false_reject``, ``reference_rejected`` (``determinism ==
  "stable_fail"``) and ``flaky`` (``determinism == "flaky"``) are optional for audits
  and required for E0, and must equal their recomputation. ``variants.jsonl`` rows:
  ``variant_id``, ``task_hash`` (of a task in tasks.jsonl), ``kind`` (``violating`` or
  ``preserving``), ``counted_in_headline``, ``witness_sha256``, ``validations
  [{validator, verdict}]``, ``grader_passed``.
* E0 (G5) uses pinned paths only; nothing about where things are is read from
  results.json. Labels ``toybench/labels.json`` = ``{"tasks": {<id>: {"planted":
  bool, "slice": "in_list" | "clean" | "extra", "weakness_type": ..., "direction":
  "accept" | "reject" | null}}}`` with ``planted == (slice != "clean")`` and a
  direction on every planted task. ``toybench/labels.sha256`` holds the labels' SHA-256
  as its first token; exactly one commit touches it, that commit predates
  ``artifacts/e0/`` and ``artifacts/model_calls/e0/``, and ``toybench/tasks/`` is
  unchanged between it and HEAD. ``artifacts/e0/tasks.jsonl`` rows also carry ``task``
  = ``<benchmark>:<id>`` (one benchmark, one row per label, ``task_hash`` = SHA-256 of
  ``task``). ``artifacts/e0/adjudication.json`` = ``{"tasks": {<id>: {"real": bool,
  ...}}}`` holds an entry for every counted task that is flagged but not detected.
  ``artifacts/e0/results.json``: ``bootstrap``, ``recall`` and ``precision`` as
  ``{point, ci: [lo, hi], n}``, ``tasks [{task: <id>, planted, slice, ...}]`` with one
  row per label (``detected``, ``flagged``, and ``adjudicated_real``, when present,
  must equal the recomputation), ``provenance``. Definitions (D23): flagged =
  false_accept or false_reject; detected = planted and (direction ``accept``:
  false_accept; ``reject``: false_reject), so a rejected or flaky reference is never a
  flag or a detection; adjudicated real = flagged, not detected, and the entry's
  ``real`` is true. Counted tasks are those whose slice is not ``extra``, in ascending
  id order. Recall = detected / planted; precision = detected / (detected + false
  positives), where a false positive is flagged, not detected, and not adjudicated
  real; ``n`` = the number of counted tasks. Every counted miss (planted, not
  detected) appears in ``docs/E0_MISSES.md`` as a whole token.
* Audits (G7) ``artifacts/audit/<benchmark>/summary.json``: ``benchmark``,
  ``category``, ``confirmatory``, ``prereg``, ``substitute_for``, ``model_store``,
  ``n_tasks_population``, ``n_sampled``, ``bootstrap``, ``e1.false_accept_task_rate``
  and ``e2.false_reject_task_rate`` as ``{point, ci, n}`` over the scorable tasks in
  tasks.jsonl order, ``provenance``.
* E4 (G8) ``artifacts/e4/<benchmark>/summary.json`` (``<benchmark>`` is the audit's
  directory name; schema ``graderproof.e4/1``): ``ran``, ``benchmark`` (the audit's
  ``benchmark``), ``repaired [{task_hash, benchmark, public, patch, validation_log}]``,
  ``unrepaired [{task_hash, reason}]``, ``generalization {ran, n_fresh_variants,
  survivors_original, caught_by_repair, survivors_repaired, induced_false_rejects,
  ...}``, ``provenance``. The repaired and unrepaired task hashes are, together and
  without repeats, exactly the audit's scorable tasks with a surviving variant. Public
  patches and logs are tracked under ``outbound/patches/``; private ones live under
  ``private/outbound/patches/`` and are listed in ``outbound/patches/MANIFEST.json``.
  Every validation log is a JSON object with ``"accepted": true`` and the entry's
  ``task_hash``.
* E5 (G9) ``artifacts/e5/<benchmark>/summary.json``: ``ran``, ``bootstrap``,
  ``pass_flips {point, ci}``, ``rank_changes {point, ci}``, ``provenance``; and
  ``rows.jsonl`` with ``{model, task_hash, trial, original_pass, repaired_pass}``
  (booleans; one row per model, task, and trial). pass_flips = rows with
  original_pass and not repaired_pass, over rows with original_pass. rank_changes =
  the number of model pairs (at least two models) whose sign of (pass rate of model i
  minus that of model j, over all rows) differs between original and repaired grading,
  compared exactly. Each interval must contain its point.
* Confirmatory artifacts (G11): every ``artifacts/**/summary.json`` with
  ``"confirmatory": true``, ``artifacts/e0/summary.json`` (which must say so), and
  ``artifacts/e0/results.json``. Each cites ``"prereg"``, and that preregistration's
  commit predates the artifact's directory, the directory named by its
  ``model_store`` field (under ``artifacts/``), and for E0 ``artifacts/model_calls/e0/``.
* Review ``artifacts/review/latest.json`` (schema in tools/review.py).
* Citations ``artifacts/citecheck.json`` (schema in .claude/agents/citation-checker.md).
* Figures ``artifacts/figures/manifest.json``: ``[{path, sha256}]`` written by make report.

Bootstrap intervals use the percentile method over tasks with ``random.Random(seed)``:
each of ``B`` replicates draws ``n`` task indices with ``rng.randrange(n)``; replicates
whose statistic is undefined (zero denominator) are dropped; the interval is the
``floor(alpha/2 * m)`` and ``ceil((1 - alpha/2) * m) - 1`` order statistics of the ``m``
kept replicates. graderproof's own statistics must use the identical procedure. When one
artifact carries two intervals, the second uses ``seed + 1`` (E0: recall ``seed``,
precision ``seed + 1``; audits: E1 ``seed``, E2 ``seed + 1``; E5: pass flips ``seed``,
rank changes ``seed + 1``). For E5 the resampled units are the distinct ``task_hash``
values in ascending order, and a replicate's statistic is computed over all rows of
every drawn task (a task drawn twice contributes its rows twice).
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

ORIGIN = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PREREG_RE = re.compile(r"^prereg/\d{4}-[a-z0-9][a-z0-9-]*\.md$")
COVERAGE_MIN = 85.0
ALPHA = 0.05
MIN_REPLICATES = 1000
DETERMINISM = ("stable_pass", "stable_fail", "flaky")
KINDS = ("violating", "preserving")
E0_MIN = 0.90
E0_MIN_TASKS = 60
E0_LABELS = "toybench/labels.json"
E0_LABELS_SHA256 = "toybench/labels.sha256"
E0_TASKS = "toybench/tasks"
E0_DIR = "artifacts/e0"
E0_MODEL_STORE = "artifacts/model_calls/e0"
E0_SUMMARY = "artifacts/e0/summary.json"
E0_RESULTS = "artifacts/e0/results.json"
E0_ADJUDICATION = "artifacts/e0/adjudication.json"
E0_MISSES = "docs/E0_MISSES.md"
E0_SLICES = ("in_list", "clean", "extra")
E0_DIRECTIONS = ("accept", "reject")
TOKEN_CHARS = "A-Za-z0-9_-"
E4_SCHEMA = "graderproof.e4/1"
E4_GENERALIZATION = (
    "n_fresh_variants",
    "survivors_original",
    "caught_by_repair",
    "survivors_repaired",
    "induced_false_rejects",
)
AUDIT_MIN_BENCHMARKS = 3
AUDIT_MIN_SAMPLE = 40
DEMO_MAX_S = 180.0
REPORT_WORDS = (4000, 8000)
CI_STEPS = ("lint", "typecheck", "test", "demo")
REVIEW_ALLOWED_PREFIXES = ("artifacts/review/",)
REVIEW_ALLOWED_FILES = ("STATUS.md", "docs/LOG.md")
REQUIRED_FILES = ("LICENSE", "CITATION.cff", "SECURITY.md", "CONTRIBUTING.md")
README_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("what it is and is not", ("what it is",)),
    ("key results", ("key results", "results")),
    ("how it works", ("how it works",)),
    ("use on your own benchmark", ("your own",)),
    ("reproduce", ("reproduc",)),
    ("limitations", ("limitation",)),
    ("responsible disclosure", ("disclosure",)),
    ("related work", ("related work",)),
    ("citation", ("citation", "cite")),
    ("license", ("license",)),
)
REPORT_SECTIONS = (
    "abstract",
    "introduction",
    "related work",
    "method",
    "experiments",
    "results",
    "limitations",
    "ethics",
    "disclosure",
    "reproducib",
)


# --------------------------------------------------------------------------- helpers


@dataclass
class Result:
    """Outcome of one gate."""

    ok: bool
    evidence: str


class GateError(Exception):
    """A gate condition that does not hold; the message is the gate's evidence."""


def need(cond: bool, message: str) -> None:
    """Raise :class:`GateError` with ``message`` unless ``cond`` holds."""
    if not cond:
        raise GateError(message)


def gate(check: Callable[[Ctx], Result]) -> Callable[[Ctx], Result]:
    """Turn a :class:`GateError` raised inside a gate into a failing :class:`Result`."""

    @functools.wraps(check)
    def run(ctx: Ctx) -> Result:
        try:
            return check(ctx)
        except GateError as exc:
            return Result(False, str(exc))

    return run


def is_int(x: Any) -> bool:
    """A JSON integer (booleans excluded)."""
    return isinstance(x, int) and not isinstance(x, bool)


def is_num(x: Any) -> bool:
    """A finite JSON number (booleans excluded)."""
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


@dataclass
class Step:
    """Outcome of one sub-command."""

    rc: int
    out: str
    seconds: float
    stdout: str = ""


@dataclass
class Ctx:
    """Shared state for one ship-check run."""

    origin: Path
    work: Path
    fast: bool
    head: str = ""
    clone: Path = field(default_factory=Path)
    steps: dict[str, Step] = field(default_factory=dict)
    origin_facts: dict[str, Any] = field(default_factory=dict)

    @property
    def logs(self) -> Path:
        return self.work / "logs"

    def run(
        self,
        name: str,
        cmd: Sequence[str],
        cwd: Path | None = None,
        timeout: float = 1800.0,
        env: Mapping[str, str] | None = None,
    ) -> Step:
        """Run a sub-command, log it to the temp dir, and remember it by ``name``."""
        self.logs.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                list(cmd),
                cwd=str(cwd or self.clone),
                env=dict(env) if env is not None else clean_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            rc, out, stdout = proc.returncode, proc.stdout + proc.stderr, proc.stdout
        except subprocess.TimeoutExpired as exc:
            rc, out, stdout = 124, f"timeout after {timeout}s: {exc}", ""
        except OSError as exc:
            rc, out, stdout = 127, f"could not start: {exc}", ""
        step = Step(rc, out, time.monotonic() - start, stdout)
        (self.logs / f"{name}.log").write_text(f"$ {' '.join(cmd)}\n{out}\nrc={rc}\n")
        self.steps[name] = step
        return step


def clean_env() -> dict[str, str]:
    """Environment for sub-commands: no activated venv, no bytecode in the origin."""
    env = dict(os.environ)
    for k in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH"):
        env.pop(k, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["UV_NO_PROGRESS"] = "1"
    return env


def git(cwd: Path, *args: str) -> tuple[int, str]:
    """Run git without taking optional locks (so the origin index is not rewritten)."""
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """Hex SHA-256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    """Parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_obj(path: Path, rel: str) -> dict[str, Any]:
    """A JSON object from ``path``; raises :class:`GateError` if missing, unparsable, or not one."""
    need(path.is_file(), f"{rel} missing")
    try:
        doc = load_json(path)
    except (OSError, ValueError) as exc:
        raise GateError(f"{rel} is not valid JSON ({one_line(str(exc), 60)})") from None
    need(isinstance(doc, dict), f"{rel} is not a JSON object")
    return dict(doc)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON-lines file (missing file means no rows)."""
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_rows(path: Path, rel: str) -> list[dict[str, Any]]:
    """JSON-lines rows that must all be objects (missing file means no rows)."""
    try:
        rows = read_jsonl(path)
    except (OSError, ValueError) as exc:
        raise GateError(f"{rel} is not valid JSON lines ({one_line(str(exc), 60)})") from None
    need(all(isinstance(r, dict) for r in rows), f"{rel} has a row that is not a JSON object")
    return rows


def rel_to(root: Path, path: Path) -> str:
    """``path`` relative to ``root``, POSIX style."""
    return path.relative_to(root).as_posix()


def clean_rel(value: Any, prefix: str) -> str | None:
    """``value`` if it is a canonical relative POSIX path under ``prefix``, else None."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != value:
        return None
    return value if value.startswith(prefix) and value != prefix.rstrip("/") else None


def commits_touching(repo: Path, path: str) -> list[str]:
    """Every commit that changed ``path``, newest first.

    git's default history simplification is used on purpose: a branch merged without
    changes of its own is not a second commit of the file.
    """
    rc, out = git(repo, "log", "--format=%H", "--", path)
    return out.splitlines() if rc == 0 and out else []


def strictly_before(repo: Path, a: str, b: str) -> bool:
    """True if commit ``a`` is a proper ancestor of commit ``b``."""
    if a == b:
        return False
    rc, _ = git(repo, "merge-base", "--is-ancestor", a, b)
    return rc == 0


def adds(repo: Path, paths: Sequence[str]) -> list[str]:
    """Commits that add a file under ``paths`` anywhere in the history (merges included)."""
    rc, out = git(
        repo, "log", "--full-history", "-m", "--diff-filter=A", "--format=%H", "--", *paths
    )
    return out.splitlines() if rc == 0 and out else []


def renames(repo: Path) -> list[tuple[str, str]]:
    """(source, destination) of every rename in the history, at 90% similarity or more.

    Only true renames count (a file deleted and a near-identical one added in the same
    commit). Copies do not: ``git log --follow`` would also follow copies, which would
    date new data by any older file that happens to look like it.
    """
    rc, out = git(
        repo, "log", "--full-history", "-m", "-M90%", "--diff-filter=R", "--name-status",
        "--format=",
    )  # fmt: skip
    pairs = []
    for line in out.splitlines() if rc == 0 else []:
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            pairs.append((parts[1], parts[2]))
    return pairs


def under(path: str, dirs: Iterable[str]) -> bool:
    """Whether ``path`` is one of ``dirs`` or inside one."""
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in dirs)


def data_commits(repo: Path, dirs: Sequence[str]) -> list[str]:
    """Every commit that brought a file into ``dirs``.

    That is every commit adding a file under them anywhere in the history (side
    branches and merges included), plus the commits that added any file later renamed
    into them (rename chains followed), so data cannot be dated by the commit that
    moved it in.
    """
    if not dirs:
        return []
    found = adds(repo, dirs)
    moves = renames(repo)
    todo = {src for src, dst in moves if under(dst, dirs)}
    seen: set[str] = set()
    while todo:
        src = todo.pop()
        if src in seen:
            continue
        seen.add(src)
        found += adds(repo, [src])
        todo |= {s for s, d in moves if d == src}
    return list(dict.fromkeys(found))


def not_after(repo: Path, anchor: str, commits: Iterable[str]) -> str | None:
    """The first of ``commits`` that ``anchor`` is not a proper ancestor of, or None."""
    return next((c for c in commits if not strictly_before(repo, anchor, c)), None)


def has_token(text: str, token: str) -> bool:
    """Whether ``token`` occurs in ``text`` with no identifier character on either side."""
    pattern = rf"(?<![{TOKEN_CHARS}]){re.escape(token)}(?![{TOKEN_CHARS}])"
    return re.search(pattern, text) is not None


def one_line(text: str, limit: int = 160) -> str:
    """Collapse whitespace and truncate for an evidence field."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def tail(out: str, n: int = 1) -> str:
    """Last ``n`` non-empty lines of command output, collapsed."""
    lines = [ln for ln in out.splitlines() if ln.strip() and "UV_NATIVE_TLS" not in ln]
    return one_line(" | ".join(lines[-n:])) if lines else "(no output)"


def fmt(x: float) -> str:
    """Format a statistic for evidence."""
    return f"{x:.3f}"


# ------------------------------------------------------------------------ statistics


Statistic = Callable[[Sequence[int]], float | None]


def bootstrap_ci(
    n: int,
    stat: Statistic,
    seed: int,
    replicates: int,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of ``stat`` over resampled task indices.

    ``stat`` takes a list of task indices and returns the statistic, or None when it
    is undefined for that resample. See the module docstring for the exact procedure.
    """
    if n <= 0 or replicates <= 0:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat(idx)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    m = len(values)
    lo = values[math.floor(alpha / 2 * m)]
    hi = values[max(0, math.ceil((1 - alpha / 2) * m) - 1)]
    return lo, hi


def ratio(num: int, den: int) -> float | None:
    """num / den, or None when den is zero."""
    return num / den if den else None


def close(a: Any, b: float, tol: float = 1e-9) -> bool:
    """Whether an artifact number ``a`` equals a recomputed ``b`` (booleans never do)."""
    return is_num(a) and abs(float(a) - b) <= tol


def close_ci(a: Any, b: tuple[float, float] | None, tol: float = 1e-9) -> bool:
    """Whether an artifact interval ``a`` equals a recomputed interval ``b``."""
    return (
        b is not None
        and isinstance(a, list)
        and len(a) == 2
        and close(a[0], b[0], tol)
        and close(a[1], b[1], tol)
    )


def bootstrap_params(obj: Mapping[str, Any], what: str = "artifact") -> tuple[int, int, float]:
    """(seed, B, alpha) from an artifact's ``bootstrap`` block; raises :class:`GateError`.

    The block must hold integer ``seed`` and ``B`` with ``B >= MIN_REPLICATES`` and
    ``alpha == 0.05``, so every interval is a 95% interval with enough replicates.
    """
    b: Any = obj.get("bootstrap")
    need(isinstance(b, Mapping), f"{what} has no bootstrap block")
    seed, reps, alpha = b.get("seed"), b.get("B"), b.get("alpha")
    need(is_int(seed) and is_int(reps), f"{what} bootstrap seed and B must be integers")
    need(reps >= MIN_REPLICATES, f"{what} bootstrap B={reps} (< {MIN_REPLICATES})")
    need(is_num(alpha) and alpha == ALPHA, f"{what} bootstrap alpha is not {ALPHA}")
    return int(seed), int(reps), float(alpha)


def check_estimate(
    stated: Any,
    point: float,
    ci: tuple[float, float] | None,
    n: int | None,
    what: str,
) -> None:
    """Raise :class:`GateError` unless ``stated`` ``{point, ci, n}`` equals the recomputation."""
    need(isinstance(stated, Mapping), f"{what} missing")
    need(
        close(stated.get("point"), point),
        f"{what} point {stated.get('point')!r} differs from the recomputed {fmt(point)}",
    )
    need(ci is not None, f"{what} interval cannot be recomputed (every replicate undefined)")
    need(
        close_ci(stated.get("ci"), ci),
        f"{what} interval {stated.get('ci')!r} differs from the recomputed "
        f"[{fmt(ci[0]) if ci else '?'}, {fmt(ci[1]) if ci else '?'}]",
    )
    if n is not None:
        need(
            is_int(stated.get("n")) and stated.get("n") == n,
            f"{what} n {stated.get('n')!r} differs from the {n} tasks recomputed",
        )


def provenance_ok(obj: Mapping[str, Any]) -> list[str]:
    """Missing provenance fields of an artifact."""
    prov = obj.get("provenance")
    if not isinstance(prov, Mapping):
        return ["provenance"]
    need = ("git_sha", "command", "created_utc")
    return [k for k in need if not prov.get(k)]


# ------------------------------------------------------------- phase A: the origin


def check_origin(ctx: Ctx) -> None:
    """Checks that must run in the original checkout (G14 tree parts, G8 manifests)."""
    rc, status = git(ctx.origin, "status", "--porcelain", "--untracked-files=all")
    ctx.origin_facts["tree_clean"] = rc == 0 and status == ""
    ctx.origin_facts["tree_dirty_count"] = len(status.splitlines()) if status else 0
    _, tracked_private = git(ctx.origin, "ls-files", "--", "private")
    ctx.origin_facts["private_tracked"] = [p for p in tracked_private.splitlines() if p]
    ctx.origin_facts["manifest"] = verify_manifest(ctx.origin)


def verify_manifest(repo: Path) -> dict[str, Any]:
    """Verify outbound/patches/MANIFEST.json entries against files under private/.

    Returns ``present``, ``entries`` (path to SHA-256), ``problems``, and ``logs``: for
    each listed JSON file whose hash matches, its ``accepted`` and ``task_hash`` fields
    (None when absent or of the wrong type). Nothing else is read from private files.
    """
    path = repo / "outbound" / "patches" / "MANIFEST.json"
    rc, _ = git(repo, "ls-files", "--error-unmatch", "outbound/patches/MANIFEST.json")
    empty: dict[str, Any] = {"present": False, "entries": {}, "problems": [], "logs": {}}
    if not path.exists() or rc != 0:
        return empty
    problems: list[str] = []
    entries: dict[str, str] = {}
    logs: dict[str, dict[str, Any]] = {}
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        return {**empty, "present": True, "problems": [f"MANIFEST.json invalid: {exc}"]}
    rows = data.get("files") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        return {**empty, "present": True, "problems": ["MANIFEST.json has no files list"]}
    for row in rows:
        if not isinstance(row, Mapping):
            problems.append("MANIFEST.json has an entry that is not an object")
            continue
        rel = str(row.get("path", ""))
        want = str(row.get("sha256", ""))
        if clean_rel(rel, "private/outbound/patches/") is None:
            problems.append(f"{rel}: not under private/outbound/patches/")
            continue
        f = repo / rel
        if not f.is_file():
            problems.append(f"{rel}: missing")
        elif not HEX64.match(want) or sha256_file(f) != want:
            problems.append(f"{rel}: sha256 mismatch")
        elif rel.endswith(".json"):
            logs[rel] = log_facts(f)
        entries[rel] = want
    return {"present": True, "entries": entries, "problems": problems, "logs": logs}


def log_facts(path: Path) -> dict[str, Any]:
    """``accepted`` and ``task_hash`` of a repair validation log (None when unusable)."""
    try:
        doc = load_json(path)
    except (OSError, ValueError):
        doc = None
    doc = doc if isinstance(doc, Mapping) else {}
    accepted, task_hash = doc.get("accepted"), doc.get("task_hash")
    return {
        "accepted": accepted if isinstance(accepted, bool) else None,
        "task_hash": task_hash if isinstance(task_hash, str) else None,
    }


def make_clone(ctx: Ctx) -> None:
    """Fresh clone of HEAD into the temp dir."""
    ctx.clone = ctx.work / "clone"
    step = ctx.run(
        "clone",
        ["git", "clone", "--quiet", "--no-hardlinks", str(ctx.origin), str(ctx.clone)],
        cwd=ctx.work,
        timeout=600,
    )
    if step.rc != 0:
        raise RuntimeError(f"git clone failed: {tail(step.out)}")
    step = ctx.run("checkout", ["git", "checkout", "--quiet", "--detach", ctx.head])
    if step.rc != 0:
        raise RuntimeError(f"git checkout failed: {tail(step.out)}")


# --------------------------------------------------------------------------- gates


def g1_build_and_tests(ctx: Ctx) -> Result:
    """make setup, make test, >= 85% line coverage on core modules."""
    setup = ctx.run("setup", ["make", "setup"], timeout=1200)
    if setup.rc != 0:
        return Result(False, f"make setup failed: {tail(setup.out)}")
    test = ctx.run("test", ["make", "test"], timeout=3600)
    junit = junit_counts(ctx.clone / "junit.xml")
    if test.rc != 0:
        return Result(False, f"make test failed: {tail(test.out)}")
    if junit is None or junit["tests"] == 0:
        return Result(False, "make test ran no tests (junit.xml missing or empty)")
    if junit["failures"] or junit["errors"]:
        return Result(False, f"junit reports failures {junit['failures']} errors {junit['errors']}")
    cov = core_coverage(ctx.clone)
    if isinstance(cov, str):
        return Result(False, cov)
    pct, n_files, excluded = cov
    ok = pct >= COVERAGE_MIN
    return Result(
        ok,
        f"setup ok; {junit['tests']} tests pass ({junit['skipped']} skipped); core line coverage "
        f"{pct:.1f}% over {n_files} files (min {COVERAGE_MIN:.0f}%); "
        f"{len(excluded)} fixture-covered adapters excluded",
    )


def junit_counts(path: Path) -> dict[str, int] | None:
    """Totals from a pytest junit.xml."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for m in re.finditer(r"<testsuite\b([^>]*)>", text):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        for k in totals:
            totals[k] += int(attrs.get(k, "0") or 0)
    return totals


def core_coverage(clone: Path) -> tuple[float, int, list[str]] | str:
    """Summed line coverage over every package module except fixture-covered adapters."""
    cov_path = clone / "coverage.json"
    if not cov_path.exists():
        return "coverage.json not written by make test"
    with (clone / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)
    excluded = list(
        pyproject.get("tool", {})
        .get("graderproof", {})
        .get("coverage", {})
        .get("external_adapters", [])
    )
    for rel in excluded:
        stem = Path(rel).stem
        if not rel.startswith("src/graderproof/adapters/"):
            return f"coverage exclusion {rel} is not an adapter"
        contract = clone / "tests" / "contract" / f"test_{stem}.py"
        fixtures = clone / "tests" / "fixtures" / stem
        if not contract.exists() or not fixtures.is_dir() or not any(fixtures.iterdir()):
            return f"excluded adapter {rel} lacks a recorded-fixture contract test"
    files = load_json(cov_path).get("files", {})
    measured = {str(Path(k).as_posix()): v for k, v in files.items()}
    package = sorted(
        p.relative_to(clone).as_posix() for p in (clone / "src" / "graderproof").rglob("*.py")
    )
    covered = statements = 0
    n = 0
    for rel in package:
        if rel in excluded:
            continue
        data = measured.get(rel)
        if data is None:
            return f"{rel} not measured by coverage"
        summary = data.get("summary", {})
        covered += int(summary.get("covered_lines", 0))
        statements += int(summary.get("num_statements", 0))
        n += 1
    if statements == 0:
        return "no statements measured"
    return 100.0 * covered / statements, n, excluded


def g2_static_quality(ctx: Ctx) -> Result:
    """ruff check, ruff format --check, mypy --strict on the package, reasons on ignores."""
    if ctx.steps.get("setup") is None or ctx.steps["setup"].rc != 0:
        return Result(False, "no environment (make setup failed)")
    problems = []
    checks = {
        "ruff-check": ["uv", "run", "--frozen", "ruff", "check", "."],
        "ruff-format": ["uv", "run", "--frozen", "ruff", "format", "--check", "."],
        "mypy": ["uv", "run", "--frozen", "mypy", "--strict", "src/graderproof"],
    }
    for name, cmd in checks.items():
        step = ctx.run(name, cmd, timeout=900)
        if step.rc != 0:
            problems.append(f"{name}: {tail(step.out)}")
    weak = mypy_weakening(ctx.clone)
    if weak:
        problems.append(f"mypy config weakened: {weak}")
    bare = bare_type_ignores(ctx.clone)
    if bare:
        problems.append(f"type: ignore without reason at {', '.join(bare[:3])}")
    if problems:
        return Result(False, "; ".join(problems))
    return Result(
        True, "ruff check, ruff format --check, mypy --strict clean; every ignore has a reason"
    )


# Flags that --strict turns on, plus checks that are on by default; setting any of them
# to false (globally or for a module) weakens the package check.
MYPY_STRICT_FLAGS = (
    "warn_unused_configs",
    "disallow_any_generics",
    "disallow_subclassing_any",
    "disallow_untyped_calls",
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "check_untyped_defs",
    "disallow_untyped_decorators",
    "warn_redundant_casts",
    "warn_unused_ignores",
    "warn_return_any",
    "no_implicit_reexport",
    "strict_equality",
    "extra_checks",
    "strict_concatenate",
    "strict_optional",
    "no_implicit_optional",
    "warn_no_return",
    "warn_unreachable",
)
# Options whose true value loosens checking.
MYPY_LOOSENING_FLAGS = (
    "ignore_errors",
    "implicit_optional",
    "implicit_reexport",
    "allow_untyped_globals",
    "allow_untyped_defs",
    "allow_untyped_calls",
    "allow_incomplete_defs",
    "allow_untyped_decorators",
    "allow_any_generics",
    "allow_subclassing_any",
)
MYPY_INLINE_RE = re.compile(r"^\s*#\s*mypy\s*:", re.M)
FILE_IGNORE_RE = re.compile(r"^\s*#\s*type\s*:\s*ignore", re.M)


def mypy_loosened(cfg: Mapping[str, Any]) -> str:
    """The first option in a mypy config table that weakens checking, or empty."""
    for key in MYPY_LOOSENING_FLAGS:
        if cfg.get(key) is True:
            return f"{key} = true"
    for key in MYPY_STRICT_FLAGS:
        if cfg.get(key) is False:
            return f"{key} = false"
    if cfg.get("disable_error_code"):
        return "disable_error_code"
    if str(cfg.get("follow_imports", "normal")) in ("skip", "silent"):
        return f"follow_imports = {cfg.get('follow_imports')}"
    return ""


def affects_package(pattern: Any) -> bool:
    """Whether a mypy override module pattern can match a ``graderproof`` module."""
    first = str(pattern).split(".", 1)[0]
    return first == "graderproof" or "*" in first


def mypy_weakening(clone: Path) -> str:
    """Config or source comments that would make mypy --strict pass vacuously.

    Checked: extra config files; in ``[tool.mypy]`` and in overrides that can match the
    package, any option that loosens checking or turns a strict check off,
    ``disable_error_code``, and ``follow_imports`` skip or silent; an ``exclude`` that
    matches a package path; and in ``src/``, inline ``# mypy:`` configuration comments,
    file-level ``# type: ignore`` lines, and ``no_type_check``.
    """
    for name in ("mypy.ini", ".mypy.ini", "setup.cfg"):
        if (clone / name).exists():
            return f"extra mypy config file {name}"
    with (clone / "pyproject.toml").open("rb") as fh:
        mypy = tomllib.load(fh).get("tool", {}).get("mypy", {})
    why = mypy_loosened(mypy)
    if why:
        return why
    for ov in mypy.get("overrides", []) or []:
        if not isinstance(ov, Mapping):
            return "malformed mypy override"
        mods = ov.get("module", [])
        mods = [mods] if isinstance(mods, str) else list(mods)
        why = mypy_loosened(ov)
        if why and any(affects_package(m) for m in mods):
            return f"{why} in the override for {mods}"
    exclude = mypy.get("exclude")
    if exclude:
        hit = excluded_package_path(clone, [exclude] if isinstance(exclude, str) else exclude)
        if hit:
            return f"exclude matches {hit}"
    return inline_weakening(clone)


def excluded_package_path(clone: Path, patterns: Iterable[Any]) -> str:
    """The first package file or directory a mypy ``exclude`` regex matches, or empty."""
    root = clone / "src" / "graderproof"
    paths = ["src/graderproof/"]
    for p in sorted(root.rglob("*")) if root.exists() else []:
        rel = rel_to(clone, p)
        paths.append(rel + "/" if p.is_dir() else rel)
    for pat in patterns:
        try:
            rx = re.compile(str(pat))
        except re.error:
            return f"(unparsable pattern {pat!r})"
        hit = next((p for p in paths if rx.search(p)), "")
        if hit:
            return hit
    return ""


def inline_weakening(clone: Path) -> str:
    """Inline mypy configuration, file-level type ignores, or no_type_check in src/."""
    src = clone / "src"
    for p in sorted(src.rglob("*.py")) if src.exists() else []:
        text = p.read_text(encoding="utf-8")
        rel = rel_to(clone, p)
        for rx, what in (
            (MYPY_INLINE_RE, "inline # mypy: comment"),
            (FILE_IGNORE_RE, "file-level type ignore"),
            (re.compile(r"\bno_type_check\b"), "no_type_check"),
        ):
            m = rx.search(text)
            if m:
                return f"{what} at {rel}:{text.count(chr(10), 0, m.start()) + 1}"
    return ""


IGNORE_RE = re.compile(r"#\s*type:\s*ignore(\[[^\]]*\])?(.*)$")


def bare_type_ignores(clone: Path) -> list[str]:
    """``type: ignore`` comments without a trailing ``# reason``."""
    hits = []
    for top in ("src", "tests", "tools"):
        for p in sorted((clone / top).rglob("*.py")) if (clone / top).exists() else []:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = IGNORE_RE.search(line)
                if m and not re.match(r"\s*#\s*\S", m.group(2)):
                    hits.append(f"{p.relative_to(clone).as_posix()}:{i}")
    return hits


def g3_ci_parity(ctx: Ctx) -> Result:
    """ci.yml runs make ci on 3.11 and 3.12; make ci covers lint/typecheck/test/demo; passes."""
    wf = workflow_problems(ctx)
    if wf:
        return Result(False, wf)
    mk = makefile_ci_problems(ctx.clone / "Makefile")
    if mk:
        return Result(False, mk)
    if ctx.fast:
        parts = {
            "lint": all(
                ctx.steps[k].rc == 0 for k in ("ruff-check", "ruff-format") if k in ctx.steps
            )
            and "ruff-check" in ctx.steps,
            "typecheck": "mypy" in ctx.steps and ctx.steps["mypy"].rc == 0,
            "test": "test" in ctx.steps and ctx.steps["test"].rc == 0,
            "demo": "demo" in ctx.steps and ctx.steps["demo"].rc == 0,
        }
        bad = [k for k, v in parts.items() if not v]
        if bad:
            return Result(False, f"ci.yml ok; make ci parts failing (fast, not rerun): {bad}")
        return Result(True, "ci.yml runs make ci on 3.11 and 3.12; parts pass (fast, not rerun)")
    step = ctx.run("ci", ["make", "ci"], timeout=3600)
    if step.rc != 0:
        return Result(False, f"make ci failed: {tail(step.out)}")
    return Result(
        True, f"ci.yml runs make ci on 3.11 and 3.12; make ci passed in {step.seconds:.0f}s"
    )


def workflow_problems(ctx: Ctx) -> str:
    """Problems with .github/workflows/ci.yml, parsed with the clone's PyYAML."""
    path = ctx.clone / ".github" / "workflows" / "ci.yml"
    if not path.exists():
        return ".github/workflows/ci.yml missing"
    code = (
        "import json,sys,yaml;"
        "print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))"
    )
    step = ctx.run("ci-yaml", ["uv", "run", "--frozen", "python", "-c", code, str(path)])
    if step.rc != 0:
        return f"ci.yml unparsable: {tail(step.out)}"
    try:
        doc = json.loads(step.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return "ci.yml unparsable"
    for job in (doc.get("jobs") or {}).values():
        matrix = ((job or {}).get("strategy") or {}).get("matrix") or {}
        versions = {str(v) for v in matrix.get("python-version", [])}
        runs = [str(s.get("run", "")) for s in (job.get("steps") or []) if isinstance(s, dict)]
        runs_ci = any(re.search(r"(^|\s|;|&&)make ci(\s|$|;|&)", r) for r in runs)
        uses_matrix = "matrix.python-version" in json.dumps(job)
        if {"3.11", "3.12"} <= versions and runs_ci and uses_matrix:
            return ""
    return "no ci.yml job runs `make ci` with a matrix over Python 3.11 and 3.12"


def makefile_ci_problems(makefile: Path) -> str:
    """Whether the ``ci`` target depends on lint, typecheck, test, and demo."""
    text = makefile.read_text(encoding="utf-8")
    m = re.search(r"^ci:([^\n#]*)", text, re.M)
    if not m:
        return "Makefile has no ci target"
    deps = m.group(1).split()
    missing = [s for s in CI_STEPS if s not in deps]
    return f"make ci does not run {missing}" if missing else ""


def network_isolation() -> tuple[list[str], str] | None:
    """A command prefix that runs a child with no network, and its name."""
    if shutil.which("unshare"):
        probe = subprocess.run(["unshare", "-rn", "true"], capture_output=True, check=False)
        if probe.returncode == 0:
            return ["unshare", "-rn"], "unshare -rn"
    if shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"], "sandbox-exec"
    return None


def g4_offline_demo(ctx: Ctx) -> Result:
    """make demo < 3 min, no network, no model calls, output equals golden."""
    if ctx.steps.get("setup") is None or ctx.steps["setup"].rc != 0:
        return Result(False, "no environment (make setup failed)")
    golden = ctx.clone / "tests" / "golden" / "demo_output.txt"
    iso = network_isolation()
    if iso is None:
        return Result(False, "cannot isolate the network for make demo on this machine")
    prefix, iso_name = iso
    env = clean_env()
    for k in list(env):
        if k.lower() in ("http_proxy", "https_proxy", "all_proxy"):
            env.pop(k)
    env.update({"UV_OFFLINE": "1", "GRADERPROOF_OFFLINE": "1", "GRADERPROOF_NO_MODEL_CALLS": "1"})
    ledger = ctx.clone / "artifacts" / "usage" / "ledger.jsonl"
    before = sha256_file(ledger) if ledger.exists() else None
    step = ctx.run("demo", [*prefix, "make", "-s", "demo"], timeout=DEMO_MAX_S * 3, env=env)
    after = sha256_file(ledger) if ledger.exists() else None
    if step.rc != 0:
        return Result(False, f"make demo failed: {tail(step.out)}")
    if before != after:
        return Result(False, "make demo changed the usage ledger (model call)")
    if step.seconds >= DEMO_MAX_S:
        return Result(False, f"make demo took {step.seconds:.0f}s (limit {DEMO_MAX_S:.0f}s)")
    if not golden.exists():
        return Result(False, "tests/golden/demo_output.txt missing")
    (ctx.logs / "demo.stdout").write_text(step.stdout)
    if step.stdout != golden.read_text(encoding="utf-8"):
        return Result(False, "make demo output differs from tests/golden/demo_output.txt")
    return Result(True, f"{step.seconds:.0f}s under {iso_name}, no ledger change, matches golden")


@dataclass(frozen=True)
class TaskRow:
    """One tasks.jsonl row with its indicators recomputed from variants.jsonl."""

    row: Mapping[str, Any]
    task_hash: str
    determinism: str
    false_accept: bool
    false_reject: bool

    @property
    def scorable(self) -> bool:
        """The grader passes the reference stably (D26)."""
        return self.determinism == "stable_pass"


def is_counted(v: Mapping[str, Any]) -> bool:
    """A variant that counts: in the headline set with a stable grader verdict."""
    return v.get("counted_in_headline") is True and isinstance(v.get("grader_passed"), bool)


def audit_table(adir: Path, where: str, require_flags: bool = False) -> list[TaskRow]:
    """Validated tasks.jsonl rows with false accepts and false rejects recomputed.

    Raises :class:`GateError` when a row is malformed, a task repeats, a variant names an
    unknown task or kind, or a stated flag differs from its recomputation (flags are
    optional unless ``require_flags``). See the module docstring for the definitions.
    """
    tasks = read_rows(adir / "tasks.jsonl", f"{where}/tasks.jsonl")
    variants = read_rows(adir / "variants.jsonl", f"{where}/variants.jsonl")
    need(bool(tasks), f"{where}/tasks.jsonl missing or empty")
    seen: set[str] = set()
    for t in tasks:
        h = t.get("task_hash")
        need(isinstance(h, str) and HEX64.match(h) is not None, f"{where}: a task lacks task_hash")
        need(h not in seen, f"{where}/tasks.jsonl lists task {str(h)[:12]} twice")
        seen.add(str(h))
        need(
            t.get("determinism") in DETERMINISM,
            f"{where}: task {str(h)[:12]} has determinism {t.get('determinism')!r}",
        )
    by_task: dict[str, list[dict[str, Any]]] = {}
    for v in variants:
        h = v.get("task_hash")
        need(h in seen, f"{where}/variants.jsonl has a variant of unknown task {str(h)[:12]}")
        need(v.get("kind") in KINDS, f"{where}: variant kind {v.get('kind')!r} not in {KINDS}")
        by_task.setdefault(str(h), []).append(v)
    out: list[TaskRow] = []
    for t in tasks:
        h, det = str(t["task_hash"]), str(t["determinism"])
        vs = [v for v in by_task.get(h, []) if is_counted(v)]
        scorable = det == "stable_pass"
        fa = scorable and any(v["kind"] == "violating" and v["grader_passed"] is True for v in vs)
        fr = scorable and any(v["kind"] == "preserving" and v["grader_passed"] is False for v in vs)
        expected = {
            "false_accept": fa,
            "false_reject": fr,
            "reference_rejected": det == "stable_fail",
            "flaky": det == "flaky",
        }
        for key, want in expected.items():
            if require_flags or key in t:
                need(
                    t.get(key) is want,
                    f"{where}: task {h[:12]} {key} is {t.get(key)!r}; recomputed from "
                    f"determinism and variants.jsonl it is {want}",
                )
        out.append(TaskRow(t, h, det, fa, fr))
    return out


@dataclass(frozen=True)
class E0Task:
    """One labeled toybench task with graderproof's recomputed flags."""

    id: str
    planted: bool
    slice: str
    flagged: bool
    detected: bool
    real: bool

    @property
    def counted(self) -> bool:
        """Counted in recall and precision (the extra slice is reported beside them)."""
        return self.slice != "extra"


def e0_labels(c: Path) -> dict[str, dict[str, Any]]:
    """The committed labels, after checking their hash, its single commit, and its date."""
    labels_path, hash_path = c / E0_LABELS, c / E0_LABELS_SHA256
    need(labels_path.is_file(), f"{E0_LABELS} missing")
    need(hash_path.is_file(), f"{E0_LABELS_SHA256} missing")
    touching = commits_touching(c, E0_LABELS_SHA256)
    need(
        len(touching) == 1,
        f"{E0_LABELS_SHA256} has {len(touching)} commits (must be committed exactly once)",
    )
    hash_commit = touching[0]
    tokens = hash_path.read_text(encoding="utf-8").split()
    need(
        bool(tokens) and HEX64.match(tokens[0]) is not None, f"{E0_LABELS_SHA256} holds no SHA-256"
    )
    need(sha256_file(labels_path) == tokens[0], f"{E0_LABELS} does not match {E0_LABELS_SHA256}")
    data = data_commits(c, [E0_DIR, E0_MODEL_STORE])
    need(bool(data), f"no committed E0 data under {E0_DIR}/ or {E0_MODEL_STORE}/")
    bad = not_after(c, hash_commit, data)
    need(
        bad is None,
        f"{E0_LABELS_SHA256} was not committed before the E0 data (commit {str(bad)[:12]} adds "
        f"files under {E0_DIR}/ or {E0_MODEL_STORE}/)",
    )
    rc, tracked = git(c, "ls-tree", "-r", "--name-only", hash_commit, "--", E0_TASKS)
    need(rc == 0 and bool(tracked), f"{E0_TASKS}/ was not committed with or before the labels hash")
    rc, changed = git(c, "diff", "--name-only", hash_commit, "HEAD", "--", E0_TASKS)
    need(
        rc == 0 and not changed,
        f"{E0_TASKS}/ changed after the labels hash commit: {changed.splitlines()[:2]}",
    )
    try:
        doc = load_json(labels_path)
    except ValueError:
        raise GateError(f"{E0_LABELS} is not valid JSON") from None
    tasks: Any = doc.get("tasks") if isinstance(doc, Mapping) else None
    need(isinstance(tasks, Mapping) and bool(tasks), f"{E0_LABELS} has no tasks")
    labels: dict[str, dict[str, Any]] = {}
    for tid, lab in tasks.items():
        need(isinstance(lab, Mapping), f"label {tid} is not an object")
        planted, sl = lab.get("planted"), lab.get("slice")
        need(isinstance(planted, bool), f"label {tid}: planted is not true or false")
        need(sl in E0_SLICES, f"label {tid}: slice {sl!r} not in {E0_SLICES}")
        need(planted == (sl != "clean"), f"label {tid}: planted={planted} contradicts slice {sl}")
        need(
            not planted or lab.get("direction") in E0_DIRECTIONS,
            f"label {tid}: planted without direction accept or reject",
        )
        labels[str(tid)] = dict(lab)
    return labels


def e0_flags(c: Path, labels: Mapping[str, Any]) -> dict[str, TaskRow]:
    """artifacts/e0/tasks.jsonl rows by label id: one per label, flags recomputed."""
    rows = audit_table(c / E0_DIR, E0_DIR, require_flags=True)
    by_id: dict[str, TaskRow] = {}
    benchmarks: set[str] = set()
    for r in rows:
        key = r.row.get("task")
        need(
            isinstance(key, str) and ":" in key,
            f"{E0_DIR}/tasks.jsonl has a row without task '<benchmark>:<id>'",
        )
        bench, tid = str(key).split(":", 1)
        benchmarks.add(bench)
        need(
            r.task_hash == sha256_text(str(key)), f"{E0_DIR}: task_hash of {key} is not its SHA-256"
        )
        need(tid not in by_id, f"{E0_DIR}/tasks.jsonl lists task {tid} twice")
        by_id[tid] = r
    need(len(benchmarks) == 1, f"{E0_DIR}/tasks.jsonl names {len(benchmarks)} benchmarks")
    missing, extra = sorted(set(labels) - set(by_id)), sorted(set(by_id) - set(labels))
    need(
        not missing and not extra,
        f"{E0_DIR}/tasks.jsonl and {E0_LABELS} differ: unaudited {missing[:3]}, "
        f"unlabeled {extra[:3]}",
    )
    return by_id


def e0_adjudication(c: Path, labels: Mapping[str, Any]) -> dict[str, bool]:
    """Rulings from artifacts/e0/adjudication.json: label id to ``real`` (a JSON boolean)."""
    doc = load_obj(c / E0_ADJUDICATION, E0_ADJUDICATION)
    tasks: Any = doc.get("tasks")
    need(isinstance(tasks, Mapping), f"{E0_ADJUDICATION} has no tasks object")
    out: dict[str, bool] = {}
    for tid, entry in tasks.items():
        need(tid in labels, f"{E0_ADJUDICATION} rules on unlabeled task {tid}")
        real = entry.get("real") if isinstance(entry, Mapping) else None
        need(isinstance(real, bool), f"{E0_ADJUDICATION}: real for {tid} is not true or false")
        out[str(tid)] = bool(real)
    return out


def e0_scores(
    labels: Mapping[str, Mapping[str, Any]],
    flags: Mapping[str, TaskRow],
    rulings: Mapping[str, bool],
) -> list[E0Task]:
    """Every labeled task in ascending id order with flags, detection, and adjudication (D23)."""
    out = []
    for tid in sorted(labels):
        lab, t = labels[tid], flags[tid]
        planted, direction = bool(lab["planted"]), lab.get("direction")
        detected = planted and (
            (direction == "accept" and t.false_accept) or (direction == "reject" and t.false_reject)
        )
        flagged = t.false_accept or t.false_reject
        real = flagged and not detected and rulings.get(tid) is True
        out.append(E0Task(tid, planted, str(lab["slice"]), flagged, detected, real))
    return out


def e0_rows_match(res: Mapping[str, Any], scores: Sequence[E0Task]) -> None:
    """results.json lists every labeled task once, consistent with the recomputation."""
    rows: Any = res.get("tasks")
    need(isinstance(rows, list), f"{E0_RESULTS} has no tasks list")
    by_id = {s.id: s for s in scores}
    seen: set[str] = set()
    for r in rows:
        tid = r.get("task") if isinstance(r, Mapping) else None
        need(isinstance(tid, str) and tid in by_id, f"{E0_RESULTS} has a row for unlabeled {tid!r}")
        need(tid not in seen, f"{E0_RESULTS} lists task {tid} twice")
        seen.add(str(tid))
        s = by_id[str(tid)]
        need(
            r.get("planted") is s.planted and r.get("slice") == s.slice,
            f"{E0_RESULTS} row {tid} disagrees with the committed labels",
        )
        for key, want in (
            ("detected", s.detected),
            ("flagged", s.flagged),
            ("adjudicated_real", s.real),
        ):
            need(
                key not in r or r[key] is want,
                f"{E0_RESULTS} row {tid}: {key} is {r.get(key)!r}, recomputed {want}",
            )
    missing = sorted(set(by_id) - seen)
    need(not missing, f"{E0_RESULTS} lacks labeled tasks {missing[:3]}")


def e0_statistics(tasks: Sequence[E0Task]) -> tuple[Statistic, Statistic]:
    """Recall and precision over resampled task indices (see the module docstring)."""

    def tp(idx: Sequence[int]) -> int:
        return sum(1 for i in idx if tasks[i].detected)

    def recall(idx: Sequence[int]) -> float | None:
        return ratio(tp(idx), sum(1 for i in idx if tasks[i].planted))

    def precision(idx: Sequence[int]) -> float | None:
        fp = sum(1 for i in idx if tasks[i].flagged and not tasks[i].detected and not tasks[i].real)
        return ratio(tp(idx), tp(idx) + fp)

    return recall, precision


@gate
def g5_tool_validity(ctx: Ctx) -> Result:
    """E0 recall and precision >= 0.90 with 95% intervals; misses explained."""
    c = ctx.clone
    need((c / E0_RESULTS).is_file(), f"{E0_RESULTS} missing (E0 not run)")
    res = load_obj(c / E0_RESULTS, E0_RESULTS)
    missing = provenance_ok(res)
    need(not missing, f"E0 results lack provenance fields {missing}")
    labels = e0_labels(c)
    flags = e0_flags(c, labels)
    rulings = e0_adjudication(c, labels)
    scores = e0_scores(labels, flags, rulings)
    e0_rows_match(res, scores)
    counted = [s for s in scores if s.counted]
    need(len(counted) >= E0_MIN_TASKS, f"E0 has {len(counted)} counted tasks (< {E0_MIN_TASKS})")
    pending = [s.id for s in counted if s.flagged and not s.detected and s.id not in rulings]
    need(not pending, f"flags without a ruling in {E0_ADJUDICATION}: {pending[:3]}")
    seed, b, alpha = bootstrap_params(res, E0_RESULTS)
    recall, precision = e0_statistics(counted)
    idx = list(range(len(counted)))
    r_pt, p_pt = recall(idx), precision(idx)
    need(r_pt is not None and p_pt is not None, "E0 recall or precision undefined")
    assert r_pt is not None and p_pt is not None
    r_ci = bootstrap_ci(len(counted), recall, seed, b, alpha)
    p_ci = bootstrap_ci(len(counted), precision, seed + 1, b, alpha)
    check_estimate(res.get("recall"), r_pt, r_ci, len(counted), "E0 recall")
    check_estimate(res.get("precision"), p_pt, p_ci, len(counted), "E0 precision")
    assert r_ci is not None and p_ci is not None
    misses = [s.id for s in counted if s.planted and not s.detected]
    need((c / E0_MISSES).is_file(), f"{E0_MISSES} missing")
    doc = (c / E0_MISSES).read_text(encoding="utf-8")
    unexplained = [m for m in misses if not has_token(doc, m)]
    ev = (
        f"recall {fmt(r_pt)} [{fmt(r_ci[0])}, {fmt(r_ci[1])}], precision {fmt(p_pt)} "
        f"[{fmt(p_ci[0])}, {fmt(p_ci[1])}], n={len(counted)}, {len(misses)} misses, "
        f"{sum(s.real for s in counted)} adjudicated real"
    )
    need(not unexplained, f"{ev}; misses not in {E0_MISSES}: {unexplained[:3]}")
    return Result(r_pt >= E0_MIN and p_pt >= E0_MIN, f"{ev} (min {E0_MIN})")


def audit_dirs(clone: Path) -> list[Path]:
    """Benchmark audit directories under artifacts/audit/."""
    root = clone / "artifacts" / "audit"
    return (
        sorted(p for p in root.iterdir() if (p / "summary.json").exists()) if root.exists() else []
    )


def all_variant_files(clone: Path) -> list[Path]:
    """Every banked variants.jsonl (E0 and audits)."""
    return sorted((clone / "artifacts").rglob("variants.jsonl"))


def validations_of(row: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """(validator, verdict) pairs of a variant; entries without a validator name are dropped."""
    vals = row.get("validations")
    out: list[tuple[str, Any]] = []
    for v in vals if isinstance(vals, list) else []:
        if isinstance(v, Mapping) and isinstance(v.get("validator"), str) and v["validator"]:
            out.append((str(v["validator"]), v.get("verdict")))
    return out


@gate
def g6_validation_integrity(ctx: Ctx) -> Result:
    """Every headline variant has two agreeing validations and a witness."""
    c = ctx.clone
    rows = [r for f in all_variant_files(c) for r in read_rows(f, rel_to(c, f))]
    headline = [r for r in rows if r.get("counted_in_headline") is True]
    need(bool(headline), "no headline variants banked (artifacts/**/variants.jsonl)")
    bad_val = bad_wit = 0
    for r in headline:
        vals = validations_of(r)
        if (
            r.get("kind") not in KINDS
            or len({name for name, _ in vals}) < 2
            or {verdict for _, verdict in vals} != {r.get("kind")}
        ):
            bad_val += 1
        if not (isinstance(r.get("witness_sha256"), str) and HEX64.match(r["witness_sha256"])):
            bad_wit += 1
    judged = agree = unsure = 0
    for r in rows:
        vals = validations_of(r)
        if len({name for name, _ in vals}) < 2:
            continue
        if all(verdict in KINDS for _, verdict in vals):
            judged += 1
            agree += len({verdict for _, verdict in vals}) == 1
        else:
            unsure += 1
    rate = agree / judged if judged else 0.0
    ev = (
        f"{len(headline)} headline variants; agreement {fmt(rate)} ({agree}/{judged} with label "
        f"verdicts); {unsure} unsure; excluded {len(rows) - len(headline)}; lacking two "
        f"agreeing validations {bad_val}; lacking witness {bad_wit}"
    )
    return Result(bad_val == 0 and bad_wit == 0, ev)


@gate
def g7_confirmatory_audit(ctx: Ctx) -> Result:
    """E1 and E2 as preregistered on >= 3 benchmarks, with intervals; substitutes justified."""
    c = ctx.clone
    dirs = audit_dirs(c)
    good: list[str] = []
    problems: list[str] = []
    categories: set[str] = set()
    decisions = (
        (c / "DECISIONS.md").read_text(encoding="utf-8") if (c / "DECISIONS.md").exists() else ""
    )
    for d in dirs:
        where = rel_to(c, d)
        try:
            s = load_obj(d / "summary.json", f"{where}/summary.json")
            name = str(s.get("benchmark", d.name))
            audit_check(c, d, s, decisions)
        except GateError as exc:
            problems.append(f"{d.name}: {exc}")
            continue
        good.append(name)
        categories.add(str(s.get("category", "")))
    if len(good) < AUDIT_MIN_BENCHMARKS:
        detail = f"; {problems[0]}" if problems else ""
        return Result(
            False, f"{len(good)} benchmarks pass E1/E2 checks (< {AUDIT_MIN_BENCHMARKS}){detail}"
        )
    if "tool-use" not in categories:
        return Result(False, f"no tool-use benchmark among {good}")
    if problems:
        return Result(False, f"{problems[0]}")
    return Result(
        True, f"E1 and E2 banked with recomputed intervals on {len(good)} benchmarks: {good}"
    )


def audit_check(c: Path, d: Path, s: Mapping[str, Any], decisions: str) -> None:
    """Raise :class:`GateError` unless one benchmark audit meets G7."""
    where = rel_to(c, d)
    missing = provenance_ok(s)
    need(not missing, f"provenance lacks {missing}")
    need(s.get("confirmatory") is True, "not marked confirmatory")
    prereg = s.get("prereg")
    need(
        isinstance(prereg, str) and PREREG_RE.match(prereg) is not None and (c / prereg).is_file(),
        "cites no existing preregistration (prereg/NNNN-<slug>.md)",
    )
    pop: Any = s.get("n_tasks_population")
    n: Any = s.get("n_sampled")
    need(is_int(pop) and is_int(n), "n_tasks_population and n_sampled must be integers")
    need(
        pop > 0 and min(AUDIT_MIN_SAMPLE, pop) <= n <= pop,
        f"sample {n} outside [min({AUDIT_MIN_SAMPLE}, population {pop}), population]",
    )
    table = audit_table(d, where)
    need(len(table) == n, f"tasks.jsonl has {len(table)} tasks, summary says {n}")
    scorable = [t for t in table if t.scorable]
    seed, b, alpha = bootstrap_params(s, "summary.json")
    for key, sub, vals, offset in (
        ("e1", "false_accept_task_rate", [t.false_accept for t in scorable], 0),
        ("e2", "false_reject_task_rate", [t.false_reject for t in scorable], 1),
    ):
        point = ratio(sum(vals), len(vals))
        need(point is not None, f"{key} has no scorable tasks")
        assert point is not None
        ci = bootstrap_ci(len(vals), mean_of(vals), seed + offset, b, alpha)
        check_estimate((s.get(key) or {}).get(sub), point, ci, len(vals), f"{key} {sub}")
    sub_for = s.get("substitute_for")
    if sub_for:
        did = str(sub_for.get("decision", "")) if isinstance(sub_for, Mapping) else ""
        need(bool(did) and did in decisions, "substitution not justified in DECISIONS.md")
        dec_commit = first_commit_containing(c, "DECISIONS.md", did)
        need(dec_commit is not None, f"substitution decision {did} not committed")
        bad = not_after(c, str(dec_commit), data_commits(c, data_dirs(where, s)))
        need(bad is None, f"substitution decision {did} not committed before data collection")


def mean_of(values: Sequence[bool]) -> Callable[[Sequence[int]], float | None]:
    """Statistic for :func:`bootstrap_ci`: the share of resampled tasks that are True."""

    def stat(idx: Sequence[int]) -> float | None:
        return ratio(sum(values[i] for i in idx), len(idx))

    return stat


def first_commit_containing(repo: Path, path: str, needle: str) -> str | None:
    """The oldest commit whose change to ``path`` added ``needle`` (git log -S)."""
    rc, out = git(repo, "log", "--reverse", "--format=%H", "-S", needle, "--", path)
    lines = out.splitlines() if rc == 0 and out else []
    return lines[0] if lines else None


@gate
def g8_repair(ctx: Ctx) -> Result:
    """E4 with generalization batch; every surviving task repaired or explained; logs accepted."""
    c = ctx.clone
    man = ctx.origin_facts.get("manifest") or {}
    need(not man.get("problems"), f"private patch manifest: {(man.get('problems') or ['?'])[0]}")
    audits = {d.name: d for d in audit_dirs(c)}
    need(bool(audits), "no audited benchmarks (artifacts/audit/*/summary.json)")
    survivors: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for name, d in audits.items():
        where = rel_to(c, d)
        s = load_obj(d / "summary.json", f"{where}/summary.json")
        names[name] = str(s.get("benchmark", name))
        survivors[name] = {t.task_hash for t in audit_table(d, where) if t.false_accept}
    total = sum(len(v) for v in survivors.values())
    need(total > 0, "no surviving variants in any audit (nothing to repair)")
    root = c / "artifacts" / "e4"
    found = {p.parent.name: p for p in sorted(root.glob("*/summary.json"))} if root.is_dir() else {}
    counts = Counter[str]()
    for name in sorted(set(found) | {n for n, s in survivors.items() if s}):
        where = f"artifacts/e4/{name}"
        need(
            name in found,
            f"{where}/summary.json missing ({len(survivors.get(name, ()))} tasks with "
            "surviving variants)",
        )
        s = load_obj(found[name], f"{where}/summary.json")
        counts.update(e4_check(c, where, s, names.get(name, name), survivors.get(name), man))
    need(counts["repaired"] > 0, "no task repaired in any benchmark (no generalization batch)")
    return Result(
        True,
        f"E4 ran on {len(found)} benchmarks; {total} tasks with surviving variants: "
        f"{counts['repaired']} repaired ({counts['public']} public, {counts['private']} "
        f"private, hashes verified, logs accepted), {counts['unrepaired']} unrepaired with "
        f"reasons; generalization {counts['fresh']} fresh variants",
    )


def e4_check(
    c: Path,
    where: str,
    s: Mapping[str, Any],
    bench: str,
    expected: set[str] | None,
    man: Mapping[str, Any],
) -> Counter[str]:
    """Raise :class:`GateError` unless an E4 summary meets G8; returns counts for evidence."""
    need(s.get("schema") == E4_SCHEMA, f"{where}: schema is not {E4_SCHEMA}")
    need(s.get("ran") is True, f"{where}: not marked ran")
    missing = provenance_ok(s)
    need(not missing, f"{where}: provenance lacks {missing}")
    need(s.get("benchmark") == bench, f"{where}: benchmark {s.get('benchmark')!r} is not {bench!r}")
    repaired: Any = s.get("repaired")
    unrepaired: Any = s.get("unrepaired")
    need(isinstance(repaired, list), f"{where}: repaired is not a list")
    need(isinstance(unrepaired, list), f"{where}: unrepaired is not a list")
    counts = Counter[str]()
    listed: list[str] = []
    for r in repaired:
        need(isinstance(r, Mapping), f"{where}: a repaired entry is not an object")
        h = r.get("task_hash")
        need(
            isinstance(h, str) and HEX64.match(h) is not None,
            f"{where}: repaired without task_hash",
        )
        need(
            r.get("benchmark") == bench, f"{where}: repaired {str(h)[:12]} names another benchmark"
        )
        public = r.get("public")
        need(
            isinstance(public, bool), f"{where}: repaired {str(h)[:12]} public is not true or false"
        )
        for key in ("patch", "validation_log"):
            repair_file(c, where, str(h), key, r.get(key), bool(public), man)
        listed.append(str(h))
        counts.update(["repaired", "public" if public else "private"])
    for u in unrepaired:
        need(isinstance(u, Mapping), f"{where}: an unrepaired entry is not an object")
        h, reason = u.get("task_hash"), u.get("reason")
        need(
            isinstance(h, str) and HEX64.match(h) is not None,
            f"{where}: unrepaired without task_hash",
        )
        need(
            isinstance(reason, str) and bool(reason.strip()),
            f"{where}: unrepaired {str(h)[:12]} has no reason",
        )
        listed.append(str(h))
        counts["unrepaired"] += 1
    twice = [h for h, k in Counter(listed).items() if k > 1]
    need(not twice, f"{where}: task {twice[0][:12] if twice else ''} listed more than once")
    if expected is not None:
        lacking, extra = sorted(expected - set(listed)), sorted(set(listed) - expected)
        need(
            not lacking,
            f"{where}: {len(lacking)} tasks with surviving variants are neither repaired nor "
            f"listed unrepaired (first {lacking[0][:12] if lacking else ''})",
        )
        need(
            not extra,
            f"{where}: {len(extra)} listed tasks have no surviving variant in the audit "
            f"(first {extra[0][:12] if extra else ''})",
        )
    if counts["repaired"]:
        gen = s.get("generalization")
        need(
            isinstance(gen, Mapping) and gen.get("ran") is True,
            f"{where}: no post-repair generalization batch",
        )
        assert isinstance(gen, Mapping)
        for key in E4_GENERALIZATION:
            need(is_int(gen.get(key)) and gen[key] >= 0, f"{where}: generalization lacks {key}")
        fresh = int(gen["n_fresh_variants"])
        need(fresh > 0, f"{where}: the generalization batch has no fresh variants")
        need(
            gen["caught_by_repair"] <= gen["survivors_original"] <= fresh
            and gen["survivors_repaired"] <= fresh
            and gen["induced_false_rejects"] <= fresh,
            f"{where}: generalization counts are inconsistent",
        )
        counts["fresh"] += fresh
    return counts


def repair_file(
    c: Path,
    where: str,
    task_hash: str,
    key: str,
    value: Any,
    public: bool,
    man: Mapping[str, Any],
) -> None:
    """Raise :class:`GateError` unless a repair's patch or validation log is where G8 wants it."""
    if public:
        rel = clean_rel(value, "outbound/patches/")
        need(
            rel is not None and (c / rel).is_file(),
            f"{where}: public {key} {value!r} missing under outbound/patches/",
        )
        facts = log_facts(c / str(rel)) if key == "validation_log" else {}
    else:
        rel = clean_rel(value, "private/outbound/patches/")
        need(
            rel is not None and rel in (man.get("entries") or {}),
            f"{where}: private {key} {value!r} not in outbound/patches/MANIFEST.json",
        )
        need(not (c / str(rel)).exists(), f"{where}: private {key} {rel} is tracked")
        facts = (man.get("logs") or {}).get(rel, {}) if key == "validation_log" else {}
    if key == "validation_log":
        need(
            facts.get("accepted") is True,
            f'{where}: validation log {rel} does not say "accepted": true',
        )
        need(
            facts.get("task_hash") == task_hash,
            f"{where}: validation log {rel} is for another task",
        )


@dataclass(frozen=True)
class E5Row:
    """One re-graded result: a model's trial on a task under both graders."""

    model: str
    task_hash: str
    trial: int | str
    original: bool
    repaired: bool


def e5_rows(path: Path, where: str) -> list[E5Row]:
    """Validated rows.jsonl of one E5 benchmark."""
    rows = read_rows(path, f"{where}/rows.jsonl")
    need(bool(rows), f"{where}/rows.jsonl missing or empty")
    out: list[E5Row] = []
    for r in rows:
        model, h, o, p = (
            r.get("model"),
            r.get("task_hash"),
            r.get("original_pass"),
            r.get("repaired_pass"),
        )
        trial: Any = r.get("trial")
        need(isinstance(model, str) and bool(model), f"{where}: a row has no model")
        need(isinstance(h, str) and HEX64.match(h) is not None, f"{where}: a row has no task_hash")
        need(
            is_int(trial) or (isinstance(trial, str) and bool(trial)),
            f"{where}: a row has no trial",
        )
        need(
            isinstance(o, bool) and isinstance(p, bool),
            f"{where}: original_pass and repaired_pass must be true or false",
        )
        out.append(E5Row(str(model), str(h), trial, bool(o), bool(p)))
    keys = Counter((r.model, r.task_hash, r.trial) for r in out)
    need(max(keys.values()) == 1, f"{where}/rows.jsonl repeats a (model, task, trial) row")
    return out


def sign(x: int) -> int:
    """-1, 0, or 1."""
    return (x > 0) - (x < 0)


def e5_statistics(rows: Sequence[E5Row]) -> tuple[int, int, Statistic, Statistic]:
    """(tasks, models, pass flips, rank changes) over resampled task indices.

    Tasks are the distinct ``task_hash`` values in ascending order; a statistic over
    indices ``idx`` uses all rows of every drawn task, once per draw. Pass rates are
    compared exactly (integer cross-multiplication).
    """
    tasks = sorted({r.task_hash for r in rows})
    models = sorted({r.model for r in rows})
    tpos = {t: i for i, t in enumerate(tasks)}
    mpos = {m: j for j, m in enumerate(models)}
    orig = [0] * len(tasks)
    flips = [0] * len(tasks)
    runs = [[0] * len(tasks) for _ in models]
    passed_o = [[0] * len(tasks) for _ in models]
    passed_r = [[0] * len(tasks) for _ in models]
    for r in rows:
        i, j = tpos[r.task_hash], mpos[r.model]
        orig[i] += r.original
        flips[i] += r.original and not r.repaired
        runs[j][i] += 1
        passed_o[j][i] += r.original
        passed_r[j][i] += r.repaired

    def pass_flips(idx: Sequence[int]) -> float | None:
        return ratio(sum(flips[i] for i in idx), sum(orig[i] for i in idx))

    def rank_changes(idx: Sequence[int]) -> float | None:
        draws = Counter(idx)
        totals = [
            tuple(
                sum(arr[i] * k for i, k in draws.items())
                for arr in (runs[j], passed_o[j], passed_r[j])
            )
            for j in range(len(models))
        ]
        if any(n == 0 for n, _, _ in totals):
            return None
        changed = 0
        for a in range(len(models)):
            for b in range(a + 1, len(models)):
                na, oa, ra = totals[a]
                nb, ob, rb = totals[b]
                changed += sign(oa * nb - ob * na) != sign(ra * nb - rb * na)
        return float(changed)

    return len(tasks), len(models), pass_flips, rank_changes


def e5_check(c: Path, edir: Path, s: Mapping[str, Any]) -> str:
    """Raise :class:`GateError` unless one E5 benchmark recomputes; returns its evidence."""
    where = rel_to(c, edir)
    missing = provenance_ok(s)
    need(not missing, f"{where}: provenance lacks {missing}")
    seed, b, alpha = bootstrap_params(s, f"{where}/summary.json")
    rows = e5_rows(edir / "rows.jsonl", where)
    n_tasks, n_models, pass_flips, rank_changes = e5_statistics(rows)
    need(n_models >= 2, f"{where}: rank changes need at least two models (found {n_models})")
    idx = list(range(n_tasks))
    out = []
    for key, stat, offset in (("pass_flips", pass_flips, 0), ("rank_changes", rank_changes, 1)):
        point = stat(idx)
        need(point is not None, f"{where}: {key} undefined (no row passes the original grader)")
        assert point is not None
        ci = bootstrap_ci(n_tasks, stat, seed + offset, b, alpha)
        check_estimate(s.get(key), point, ci, None, f"{where} {key}")
        assert ci is not None
        need(ci[0] <= point <= ci[1], f"{where} {key} interval does not contain its point")
        out.append(f"{key} {fmt(point)} [{fmt(ci[0])}, {fmt(ci[1])}]")
    return f"{edir.name}: {', '.join(out)} over {n_tasks} tasks and {n_models} models"


@gate
def g9_impact_and_cards(ctx: Ctx) -> Result:
    """E5 on >= 1 benchmark, recomputed; a grader card per audited benchmark, aggregates only."""
    c = ctx.clone
    root = c / "artifacts" / "e5"
    ran: list[str] = []
    for p in sorted(root.glob("*/summary.json")) if root.is_dir() else []:
        s = load_obj(p, rel_to(c, p))
        if s.get("ran") is True:
            ran.append(e5_check(c, p.parent, s))
    need(bool(ran), "no E5 impact artifact that ran (artifacts/e5/<benchmark>/summary.json)")
    dirs = audit_dirs(c)
    need(bool(dirs), "no audited benchmarks to card")
    for d in dirs:
        bench = str(load_obj(d / "summary.json", rel_to(c, d)).get("benchmark", d.name))
        md, js = c / "docs" / "cards" / f"{bench}.md", c / "docs" / "cards" / f"{bench}.json"
        need(
            md.exists() and js.exists(),
            f"grader card for {bench} missing (docs/cards/{bench}.md/.json)",
        )
        card = load_obj(js, rel_to(c, js))
        leak = card_leak(bench, card, md.read_text(encoding="utf-8"), d)
        need(not leak, f"card {bench}: {leak}")
    return Result(True, f"E5 recomputed: {'; '.join(ran)}; {len(dirs)} cards, aggregates only")


TASK_KEYS = {"tasks", "task_ids", "variants", "witnesses", "surviving_variants"}


def card_leak(bench: str, card: Mapping[str, Any], md: str, adir: Path) -> str:
    """Task-level detail for unfixed tasks in a card, or empty.

    Sensitive tasks are those with a false accept or false reject and those whose
    reference the grader rejects or is flaky on, unless listed as fixed upstream.
    """
    bad = TASK_KEYS & set(card)
    if bad:
        return f"task-level keys {sorted(bad)}"
    fixed = {sha256_text(f"{bench}:{t}") for t in card.get("fixed_upstream_tasks", [])}
    sensitive = {
        t.task_hash
        for t in audit_table(adir, adir.name)
        if t.false_accept or t.false_reject or not t.scorable
    } - fixed
    text = md + json.dumps(card)
    for tok in set(re.findall(r"[A-Za-z0-9_\-./:]+", text)):
        if sha256_text(f"{bench}:{tok}") in sensitive or tok in sensitive:
            return "names a flagged task not fixed upstream"
    return ""


def g10_claim_integrity(ctx: Ctx) -> Result:
    """make claimcheck and make freshness pass on README.md and docs/REPORT.md."""
    c = ctx.clone
    if not (c / "docs" / "REPORT.md").exists():
        return Result(False, "docs/REPORT.md missing")
    out = []
    for name in ("claimcheck", "freshness"):
        step = ctx.run(name, ["make", "-s", name], timeout=1800)
        if step.rc != 0:
            return Result(False, f"make {name} failed: {tail(step.out)}")
        for doc in ("README.md", "docs/REPORT.md"):
            if doc not in step.out:
                return Result(False, f"make {name} did not report on {doc}")
        out.append(tail(step.out))
    return Result(True, "; ".join(out))


def data_dirs(where: str, s: Mapping[str, Any]) -> list[str]:
    """Directories whose files date a confirmatory artifact (see the module docstring)."""
    dirs = [where]
    store = s.get("model_store")
    if store not in (None, ""):
        store_rel = clean_rel(str(store).rstrip("/"), "artifacts/")
        need(
            isinstance(store, str) and store_rel is not None,
            f"{where}: model_store {store!r} is not a directory under artifacts/",
        )
        dirs.append(str(store_rel))
    if where == E0_DIR or where.startswith(E0_DIR + "/"):
        dirs.append(E0_MODEL_STORE)
    return list(dict.fromkeys(dirs))


def confirmatory_artifacts(clone: Path) -> list[Path]:
    """Every summary.json under artifacts/ marked confirmatory, plus the E0 files.

    An unreadable summary.json is included so that G11 fails on it rather than skip it.
    """
    found = []
    for p in sorted((clone / "artifacts").rglob("summary.json")):
        try:
            doc = load_json(p)
        except (OSError, ValueError):
            found.append(p)
            continue
        if rel_to(clone, p) == E0_SUMMARY or (isinstance(doc, Mapping) and doc.get("confirmatory")):
            found.append(p)
    if (clone / E0_RESULTS).is_file():
        found.append(clone / E0_RESULTS)
    return found


def frozen_hashes(clone: Path) -> dict[str, str]:
    """File name to SHA-256 from prereg/FROZEN.jsonl (empty if missing or unreadable)."""
    try:
        rows = read_jsonl(clone / "prereg" / "FROZEN.jsonl")
    except (OSError, ValueError):
        return {}
    return {str(e.get("file")): str(e.get("sha256")) for e in rows if isinstance(e, Mapping)}


@gate
def g11_prereg_integrity(ctx: Ctx) -> Result:
    """make prereg-verify; prereg commits predate the data; no prereg edited after freeze."""
    c = ctx.clone
    step = ctx.run("prereg-verify", ["make", "-s", "prereg-verify"], timeout=600)
    need(step.rc == 0, f"make prereg-verify failed: {tail(step.out)}")
    preregs = sorted(
        rel_to(c, p) for p in (c / "prereg").glob("*.md") if PREREG_RE.match(rel_to(c, p))
    )
    need(bool(preregs), "no preregistrations")
    frozen = frozen_hashes(c)
    commit_of: dict[str, str] = {}
    for rel in preregs:
        commits = commits_touching(c, rel)
        need(len(commits) == 1, f"{rel} has {len(commits)} commits (changed after it was frozen?)")
        need(
            frozen.get(PurePosixPath(rel).name) == sha256_file(c / rel),
            f"{rel} does not match its prereg/FROZEN.jsonl entry",
        )
        commit_of[rel] = commits[0]
    arts = confirmatory_artifacts(c)
    need(bool(arts), "no confirmatory artifacts")
    for a in arts:
        rel = rel_to(c, a)
        s = load_obj(a, rel)
        if rel == E0_SUMMARY:
            need(s.get("confirmatory") is True, f"{rel} is not marked confirmatory")
        cited = s.get("prereg")
        need(cited in commit_of, f"{rel} cites no frozen preregistration (prereg/NNNN-<slug>.md)")
        where = PurePosixPath(rel).parent.as_posix()
        dirs = data_dirs(where, s)
        data = data_commits(c, dirs)
        need(bool(data), f"{rel}: nothing committed under {dirs}")
        bad = not_after(c, commit_of[str(cited)], data)
        need(
            bad is None,
            f"{cited} does not predate the data of {rel} (commit {str(bad)[:12]} adds files "
            f"under {', '.join(dirs)})",
        )
    return Result(
        True,
        f"{len(preregs)} preregistrations frozen; {len(arts)} confirmatory artifacts "
        f"follow them; {tail(step.out)}",
    )


def g12_independent_review(ctx: Ctx) -> Result:
    """Latest review is REVIEW: SHIP for the current code; non-blocking issues logged."""
    c = ctx.clone
    path = c / "artifacts" / "review" / "latest.json"
    if not path.exists():
        return Result(False, "no review yet (artifacts/review/latest.json missing)")
    step = ctx.run(
        "review-validate", ["python3", "tools/review.py", "--validate-only"], timeout=300
    )
    last = [ln for ln in step.out.splitlines() if ln.strip()][-1:] or [""]
    if last[0].strip() != "REVIEW: SHIP":
        return Result(False, f"latest review ends with {last[0].strip() or 'nothing'!r}")
    review = load_json(path)
    if review.get("blocking"):
        return Result(False, "open blocking issues")
    sha = str(review.get("reviewed_commit", ""))
    rc, names = git(c, "diff", "--name-only", sha, "HEAD")
    if rc != 0:
        return Result(False, "reviewed commit not in history")
    stray = [
        n
        for n in names.splitlines()
        if n and not (n.startswith(REVIEW_ALLOWED_PREFIXES) or n in REVIEW_ALLOWED_FILES)
    ]
    if stray:
        return Result(False, f"code changed since review: {stray[:3]}")
    log = c / "docs" / "REVIEW_LOG.md"
    nb = review.get("non_blocking") or []
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    unlisted = [
        i.get("id") for i in nb if str(i.get("id")) not in text or str(i.get("title")) not in text
    ]
    if unlisted:
        return Result(False, f"non-blocking issues not in docs/REVIEW_LOG.md: {unlisted[:3]}")
    return Result(True, f"REVIEW: SHIP for {sha[:12]}; 0 blocking; {len(nb)} non-blocking logged")


def headings(md: str) -> list[str]:
    """Markdown ATX headings (outside fenced code), lowercased."""
    out, fenced = [], False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and re.match(r"^#{1,6}\s", line):
            out.append(line.lstrip("#").strip().lower())
    return out


def section(md: str, keyword: str) -> str:
    """Text of the first section whose heading contains ``keyword``."""
    lines = md.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m and start is None and keyword in m.group(2).lower():
            start, level = i + 1, len(m.group(1))
            continue
        if m and start is not None and level is not None and len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    return "\n".join(lines[start:]) if start is not None else ""


def readme_problems(clone: Path) -> str:
    """Section 11 structure of README.md, or empty if it complies."""
    readme = clone / "README.md"
    brief = clone / "docs" / "BUILD_BRIEF.md"
    if not readme.exists():
        return "README.md missing"
    md = readme.read_text(encoding="utf-8")
    if brief.exists() and md == brief.read_text(encoding="utf-8"):
        return "README.md is still the build brief"
    if EM_DASH in md:
        return "README.md contains an em dash"
    lines = md.splitlines()
    if not lines or not re.match(r"^#\s+graderproof\b", lines[0]):
        return "README.md does not start with '# graderproof'"
    first = "\n".join(lines[:60])
    if not re.search(r"\[\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+\s*\]|\d+%\s*CI", first):
        return "first screen has no finding with a confidence interval"
    svg = re.search(r"!\[[^\]]*\]\(([^)\s]+\.svg)\)", first)
    if not svg:
        return "first screen has no SVG headline figure"
    fig = clone / svg.group(1)
    manifest = clone / "artifacts" / "figures" / "manifest.json"
    if not fig.exists() or not manifest.exists():
        return "headline figure or artifacts/figures/manifest.json missing"
    listed = {str(e.get("path")): str(e.get("sha256")) for e in load_json(manifest)}
    if listed.get(svg.group(1)) != sha256_file(fig):
        return "headline figure is not the one make report generated"
    if not re.search(r"^\|.*\|\s*$\n^\|[\s:|-]+\|\s*$", first, re.M):
        return "first screen has no table"
    qs = section(md, "quickstart")
    if "```" not in qs or "quickstart" not in first.lower():
        return "first screen has no quickstart with a code block"
    heads = headings(md)
    pos = 0
    for label, keys in README_SECTIONS:
        found = next((i for i in range(pos, len(heads)) if any(k in heads[i] for k in keys)), None)
        if found is None:
            return f"README.md lacks section '{label}' (in order)"
        pos = found + 1
    results = section(md, "key results") or section(md, "results")
    if "artifacts/" not in results or "prereg/" not in results:
        return "key results do not link artifacts and preregistrations"
    how = section(md, "how it works")
    if "```mermaid" not in how and not re.search(r"!\[[^\]]*\]\(", how):
        return "how it works has no diagram"
    return ""


def report_problems(clone: Path) -> str:
    """Completeness of docs/REPORT.md, or empty."""
    path = clone / "docs" / "REPORT.md"
    if not path.exists():
        return "docs/REPORT.md missing"
    md = path.read_text(encoding="utf-8")
    if EM_DASH in md:
        return "docs/REPORT.md contains an em dash"
    heads = " | ".join(headings(md))
    missing = [s for s in REPORT_SECTIONS if s not in heads]
    if missing:
        return f"docs/REPORT.md lacks sections {missing}"
    prose = re.sub(r"```.*?```", " ", md, flags=re.S)
    words = len(re.findall(r"\b[\w'-]+\b", prose))
    if not REPORT_WORDS[0] <= words <= REPORT_WORDS[1]:
        return f"docs/REPORT.md has {words} words (needs {REPORT_WORDS[0]} to {REPORT_WORDS[1]})"
    figs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", md)
    if not figs:
        return "docs/REPORT.md has no figures"
    for f in figs:
        if not (path.parent / f).exists() and not (clone / f).exists():
            return f"docs/REPORT.md figure {f} missing"
    return ""


URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")


def cited_urls(clone: Path) -> list[str]:
    """External URLs cited in README.md and docs/REPORT.md (not this repository's own)."""
    urls: list[str] = []
    for rel in ("README.md", "docs/REPORT.md"):
        p = clone / rel
        if p.exists():
            urls += URL_RE.findall(p.read_text(encoding="utf-8"))
    own = "github.com/raj200501/graderproof"
    return sorted({u.rstrip(".,;") for u in urls if own not in u})


def citecheck_problems(clone: Path, urls: Sequence[str]) -> str:
    """Every cited URL has a verified entry in artifacts/citecheck.json."""
    path = clone / "artifacts" / "citecheck.json"
    if not path.exists():
        return "artifacts/citecheck.json missing"
    entries = load_json(path).get("entries", [])
    verified = set()
    for e in entries:
        if e.get("status") == "verified" and e.get("retrieved_utc") and e.get("page_title"):
            for u in (str((e.get("claimed") or {}).get("url", "")), str(e.get("final_url", ""))):
                if u:
                    verified.add(u.rstrip("/"))
    unverified = [u for u in urls if u.rstrip("/") not in verified]
    return f"unverified references {unverified[:3]}" if unverified else ""


def g13_documentation(ctx: Ctx) -> Result:
    """README follows section 11, REPORT complete, every reference verified."""
    c = ctx.clone
    for check in (readme_problems, report_problems):
        why = check(c)
        if why:
            return Result(False, why)
    step = ctx.run("citecheck", ["make", "-s", "citecheck"], timeout=600)
    if step.rc != 0:
        return Result(False, f"make citecheck failed: {tail(step.out)}")
    urls = cited_urls(c)
    if not urls:
        return Result(False, "no references cited")
    why = citecheck_problems(c, urls)
    if why:
        return Result(False, why)
    return Result(True, f"README section 11 ok; REPORT complete; {len(urls)} references verified")


def g14_hygiene(ctx: Ctx) -> Result:
    """secrets-scan clean, budget cash 0 and caps kept, private/ untracked, files, clean tree."""
    c = ctx.clone
    problems = []
    if not ctx.origin_facts.get("tree_clean"):
        problems.append(
            f"working tree not clean ({ctx.origin_facts.get('tree_dirty_count')} paths)"
        )
    if ctx.origin_facts.get("private_tracked"):
        problems.append(f"private/ tracked: {ctx.origin_facts['private_tracked'][:2]}")
    missing = [f for f in REQUIRED_FILES if not (c / f).is_file()]
    if missing:
        problems.append(f"missing {missing}")
    scan = ctx.run("secrets-scan", ["make", "-s", "secrets-scan"], timeout=900)
    if scan.rc != 0:
        problems.append(f"secrets-scan: {tail(scan.out)}")
    budget = ctx.run("budget", ["make", "-s", "budget"], timeout=300)
    if budget.rc != 0 or not re.search(r"^cash_usd = 0$", budget.out, re.M):
        problems.append(f"budget: {tail(budget.out)}")
    try:
        with (c / "budget.toml").open("rb") as fh:
            if tomllib.load(fh).get("cash_usd") != 0:
                problems.append("budget.toml cash_usd != 0")
    except (OSError, tomllib.TOMLDecodeError):
        problems.append("budget.toml unreadable")
    if problems:
        return Result(False, "; ".join(problems))
    return Result(
        True, f"{tail(scan.out)}; cash_usd = 0, caps kept; private/ untracked; tree clean"
    )


GATES: tuple[tuple[int, Callable[[Ctx], Result]], ...] = (
    (1, g1_build_and_tests),
    (2, g2_static_quality),
    (4, g4_offline_demo),
    (3, g3_ci_parity),
    (5, g5_tool_validity),
    (6, g6_validation_integrity),
    (7, g7_confirmatory_audit),
    (8, g8_repair),
    (9, g9_impact_and_cards),
    (10, g10_claim_integrity),
    (11, g11_prereg_integrity),
    (12, g12_independent_review),
    (13, g13_documentation),
    (14, g14_hygiene),
)


def run_all(ctx: Ctx) -> dict[int, Result]:
    """Phase A in the origin, then every gate in a fresh clone."""
    results: dict[int, Result] = {}
    check_origin(ctx)
    try:
        make_clone(ctx)
    except RuntimeError as exc:
        return {n: Result(False, str(exc)) for n, _ in GATES}
    for n, gate in GATES:
        try:
            results[n] = gate(ctx)
        except Exception as exc:  # a crashing check is a failing gate, never a pass
            results[n] = Result(
                False, f"check error {type(exc).__name__}: {one_line(str(exc), 100)}"
            )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="graderproof ship-check (G1 to G14)")
    ap.add_argument("--fast", action="store_true", help="skip slow steps; result does not count")
    ap.add_argument("--keep", action="store_true", help="keep the temporary clone")
    args = ap.parse_args(argv)
    rc, head = git(ORIGIN, "rev-parse", "HEAD")
    if rc != 0:
        print("ship-check: not a git checkout", file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="graderproof-ship-"))
    ctx = Ctx(origin=ORIGIN, work=work, fast=args.fast, head=head)
    print(f"HEAD {head} fresh-clone", flush=True)
    results = run_all(ctx)
    passed = 0
    for n in range(1, 15):
        r = results.get(n, Result(False, "not run"))
        passed += r.ok
        print(f"G{n} {'PASS' if r.ok else 'FAIL'} {one_line(r.evidence)}", flush=True)
    if not args.keep and ctx.clone != Path() and ctx.clone.exists():
        shutil.rmtree(ctx.clone, ignore_errors=True)
    print(f"ship-check: logs in {ctx.logs}", file=sys.stderr)
    if args.fast:
        print(f"SHIP-CHECK-FAST (does not count): {passed}/14")
        return 0 if passed == 14 else 1
    print("SHIP-CHECK: PASS 14/14" if passed == 14 else f"SHIP-CHECK: FAIL {passed}/14")
    return 0 if passed == 14 else 1


if __name__ == "__main__":
    raise SystemExit(main())
