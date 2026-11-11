"""BFCL V4 AST categories in Python as toybench ``data`` tasks (DECISIONS.md D18, D19).

The Berkeley Function Calling Leaderboard (gorilla, ``berkeley-function-call-leaderboard``,
Apache-2.0) grades a model's function calls with ``ast_checker`` against a "possible
answer" that lists the acceptable values of every argument. Each BFCL entry of the eight
Python AST categories becomes one toybench task directory of kind ``data``::

    <id>/
      task.toml               id, benchmark, kind = "data", third_party, [metadata]
      instruction.md          the request messages and the function documentation
      solution/trajectory.json  reference calls [{"tool": name, "args": {...}}]
      support/run_solution.sh   copies the solution to .gp/trajectory.json
      grader/grade.sh           runs bfcl_driver.py with $GP_BFCL_PYTHON
      grader/bfcl_driver.py     calls BFCL's own ast_checker (see bfcl_driver)
      grader/bfcl_task.json     function docs, possible answer, category, model name

BFCL has no reference solution. The reference is built from the possible answer, which
is grader data (``reference_calls``), so ``[metadata] reference_from_grader_data`` is
true. Graders run BFCL's checker from a pinned checkout, named at run time by the
environment variables ``GP_BFCL_ROOT`` and ``GP_BFCL_PYTHON`` that
``ToybenchAdapter(extra_env=...)`` passes to the sandbox. Third-party code never runs
on the host: this module only reads BFCL's JSON data files and runs ``git``.

Command line: ``python -m graderproof.adapters.bfcl fetch|convert|check``. See
docs/adapters/bfcl.md.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graderproof.adapters import bfcl_driver
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, canonical_json, sha256_text
from graderproof.run import Runner
from graderproof.sandbox import Sandbox, best_sandbox

BENCHMARK = "bfcl"
REPO_URL = "https://github.com/ShishirPatil/gorilla.git"
PINNED_COMMIT = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
"""Head of gorilla's default branch on 2026-11-04 (committed 2026-03-23, bfcl-eval 2026.3.23)."""
BFCL_DIR = "berkeley-function-call-leaderboard"
DATA_DIR = Path("bfcl_eval", "data")
VERSION_PREFIX = "BFCL_v4"
LICENSE = "Apache-2.0"
CATEGORIES = (
    "simple_python",
    "multiple",
    "parallel",
    "parallel_multiple",
    "live_simple",
    "live_multiple",
    "live_parallel",
    "live_parallel_multiple",
)
LANGUAGE = "python"
CHECKER_MODEL = "gorilla-openfunctions-v2"
"""Model name given to ``ast_checker``. Its ``underscore_to_dot`` is false at the pinned
commit, so function names are compared as written in the documentation."""
PYTHON_HINT = " Note that the provided function is in Python 3 syntax."
"""Appended to every function description by BFCL's inference loader for Python
categories (``_get_language_specific_hint`` in ``bfcl_eval/utils.py``)."""
OMIT = ""
"""BFCL's marker, in a list of acceptable values, for "this argument may be omitted"."""
TASK_TIMEOUT_S = 20
SOLUTION_FILE = "trajectory.json"
RUN_SOLUTION = "run_solution.sh"
GRADER_ENTRY = "grade.sh"
TASK_DATA = "bfcl_task.json"
DRIVER_FILE = "bfcl_driver.py"
ENV_ROOT, ENV_PYTHON = "GP_BFCL_ROOT", "GP_BFCL_PYTHON"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

RUN_SOLUTION_SH = """\
#!/usr/bin/env bash
# graderproof BFCL adapter: the solution is data, the decoded function calls.
# Copy them to .gp/trajectory.json, where toybench records them and the grader reads them.
set -eu
mkdir -p .gp
cp "$GP_SOLUTION_DIR/trajectory.json" .gp/trajectory.json
"""

GRADE_SH = """\
#!/usr/bin/env bash
# graderproof BFCL adapter: grade .gp/trajectory.json with BFCL's own AST checker.
# GP_BFCL_ROOT is the berkeley-function-call-leaderboard directory of the pinned checkout;
# GP_BFCL_PYTHON is the interpreter that runs the checker (default python3).
# Exit status: 0 valid, 1 invalid, 2 setup error, 3 the checker raised.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${GP_BFCL_PYTHON:-python3}" -I "$here/bfcl_driver.py" "$here/bfcl_task.json" \\
  .gp/trajectory.json
"""


# ------------------------------------------------------------------ source and records


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, env=env
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[-500:]}")
    return proc


def fetch(dest: Path, commit: str = PINNED_COMMIT, url: str = REPO_URL) -> Path:
    """Check out ``commit`` of gorilla in ``dest`` and return its BFCL directory.

    The checkout is shallow, blobless, and sparse (only ``berkeley-function-call-leaderboard``
    and the files at the top level, among them ``LICENSE``). An existing checkout in
    ``dest`` is reused and moved to ``commit`` if needed. Raises FileExistsError if
    ``dest`` is a non-empty directory that is not a git checkout, and RuntimeError if git
    fails or ``HEAD`` is not ``commit`` afterwards. No code from the repository is run.
    """
    if not (dest / ".git").exists():
        if dest.exists() and any(dest.iterdir()):
            raise FileExistsError(f"{dest} exists and is not a git checkout")
        dest.mkdir(parents=True, exist_ok=True)
        _git(dest, "init", "--quiet")
        _git(dest, "remote", "add", "origin", url)
        _git(dest, "sparse-checkout", "set", BFCL_DIR)
    if _git(dest, "rev-parse", "--verify", "--quiet", "HEAD", check=False).stdout.strip() != commit:
        _git(dest, "fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", commit)
        _git(dest, "checkout", "--quiet", "--detach", commit)
    return verify_checkout(dest, commit)


def verify_checkout(dest: Path, commit: str = PINNED_COMMIT) -> Path:
    """The BFCL directory of the git checkout ``dest``, which must be at ``commit``.

    Raises RuntimeError if ``HEAD`` is another commit or the BFCL data directory is
    missing.
    """
    head = _git(dest, "rev-parse", "HEAD").stdout.strip()
    if head != commit:
        raise RuntimeError(f"{dest}: HEAD is {head}, expected {commit}")
    root = dest / BFCL_DIR
    if not (root / DATA_DIR).is_dir():
        raise RuntimeError(f"{root} has no {DATA_DIR.as_posix()} directory")
    return root


def bfcl_root(source_root: Path) -> Path:
    """The ``berkeley-function-call-leaderboard`` directory: ``source_root`` or its child."""
    child = source_root / BFCL_DIR
    return child if child.is_dir() else source_root


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError(f"{path}:{n}: not a JSON object with a string id")
        entries.append(entry)
    return entries


def _check_entry(question: Mapping[str, Any], answer: Mapping[str, Any], category: str) -> None:
    ident = str(question["id"])
    if not _SAFE_ID.fullmatch(ident) or not ident.startswith(category + "_"):
        raise ValueError(f"unexpected {category} id {ident!r}")
    turns = question.get("question")
    if not isinstance(turns, list) or not all(
        isinstance(t, list)
        and all(isinstance(m, dict) and isinstance(m.get("content"), str) for m in t)
        for t in turns
    ):
        raise ValueError(f"{ident}: question is not a list of turns of messages")
    functions = question.get("function")
    if not isinstance(functions, list) or not all(
        isinstance(f, dict) and isinstance(f.get("name"), str) for f in functions
    ):
        raise ValueError(f"{ident}: function is not a list of named function documents")
    truth = answer.get("ground_truth")
    if not isinstance(truth, list) or not all(
        isinstance(c, dict)
        and len(c) == 1
        and all(
            isinstance(p, dict) and all(isinstance(v, list) for v in p.values()) for p in c.values()
        )
        for c in truth
    ):
        raise ValueError(f"{ident}: ground_truth is not a list of {{name: {{param: [values]}}}}")


def data_paths(category: str) -> tuple[Path, Path]:
    """Question and possible-answer files of ``category``, relative to the BFCL directory."""
    name = f"{VERSION_PREFIX}_{category}.json"
    return DATA_DIR / name, DATA_DIR / "possible_answer" / name


def read_records(source_root: Path, category: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """``(question entry, possible-answer entry)`` pairs of one category, in file order.

    Raises ValueError for a category outside :data:`CATEGORIES`, a malformed entry, a
    duplicate id, or a question without exactly one answer (or the reverse).
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; expected one of {', '.join(CATEGORIES)}")
    root = bfcl_root(source_root)
    q_rel, a_rel = data_paths(category)
    questions, answers = _read_jsonl(root / q_rel), _read_jsonl(root / a_rel)
    by_id = {a["id"]: a for a in answers}
    ids = [q["id"] for q in questions]
    if len(set(ids)) != len(ids) or len(by_id) != len(answers) or set(ids) != set(by_id):
        raise ValueError(f"{category}: question and possible-answer ids do not match one to one")
    pairs = [(q, by_id[q["id"]]) for q in questions]
    for q, a in pairs:
        _check_entry(q, a, category)
    return pairs


# --------------------------------------------------------------- reference construction


def _first_value(values: Sequence[Any]) -> Any:
    for value in values:
        if value != OMIT:
            return value
    return OMIT


def _is_pattern(value: Any) -> bool:
    """Whether ``value`` is a BFCL dict answer pattern: key to a list of acceptable values."""
    return isinstance(value, dict) and all(isinstance(v, list) for v in value.values())


def _from_pattern(pattern: Mapping[str, Sequence[Any]]) -> dict[str, Any]:
    return {k: _first_value(v) for k, v in pattern.items() if v and OMIT not in v}


def reference_value(values: Sequence[Any], schema: Mapping[str, Any]) -> Any:
    """The reference value of an argument from its acceptable values and its schema.

    The first acceptable value other than BFCL's omission marker ``""`` (the marker
    itself only when it is the only value). For a parameter documented as ``dict``, or
    as an ``array`` or ``tuple`` of ``dict`` items, the acceptable value is a pattern
    (key to acceptable values, as BFCL's ``dict_checker`` reads it), and the reference
    takes the first acceptable value of every key whose values do not include ``""``.
    """
    value = _first_value(values)
    kind = schema.get("type")
    items = schema.get("items")
    item_kind = items.get("type") if isinstance(items, dict) else None
    if kind == "dict" and _is_pattern(value):
        return _from_pattern(value)
    if (
        kind in ("array", "tuple")
        and item_kind == "dict"
        and isinstance(value, list)
        and value
        and all(_is_pattern(v) for v in value)
    ):
        return [_from_pattern(v) for v in value]
    return value


def reference_args(
    params: Mapping[str, Sequence[Any]], doc: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Reference arguments of one expected call (``doc`` is the function's documentation).

    An argument is omitted when it has no acceptable value, or when its acceptable
    values include ``""`` and the documentation does not list it as required. Every
    other argument takes :func:`reference_value`.
    """
    parameters = (doc or {}).get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    properties = parameters.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = parameters.get("required")
    required = set(required) if isinstance(required, list) else set()
    args: dict[str, Any] = {}
    for name, values in params.items():
        if not values or (OMIT in values and name not in required):
            continue
        schema = properties.get(name)
        args[name] = reference_value(values, schema if isinstance(schema, dict) else {})
    return args


def reference_calls(
    functions: Sequence[Mapping[str, Any]], ground_truth: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The reference solution: one ``{"tool", "args"}`` call per expected call, in order."""
    docs = {str(f["name"]): f for f in functions}
    calls = []
    for expected in ground_truth:
        ((name, params),) = expected.items()
        calls.append({"tool": name, "args": reference_args(params, docs.get(name))})
    return calls


# ------------------------------------------------------------------ task directories


def with_python_hint(functions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Function documentation as BFCL's inference loader gives it to the model (Python)."""
    out = [copy.deepcopy(dict(f)) for f in functions]
    for f in out:
        f["description"] = str(f.get("description", "")) + PYTHON_HINT
    return out


def _fence(text: str, info: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{info}\n{text}\n{ticks}"


def instruction(question: Mapping[str, Any]) -> str:
    """``instruction.md``: the request messages and the function documentation, verbatim."""
    parts = [
        "# Function calling task (BFCL)",
        "",
        "Answer the request below by calling one or more of the functions documented after it.",
        "",
        "## Request",
    ]
    messages = [m for turn in question["question"] for m in turn]
    for i, m in enumerate(messages, start=1):
        parts += [
            "",
            f"### Message {i} ({m.get('role', 'user')})",
            "",
            _fence(m["content"], "text"),
        ]
    docs = json.dumps(with_python_hint(question["function"]), indent=2, ensure_ascii=False)
    parts += [
        "",
        "## Functions",
        "",
        "The functions you can call, documented in JSON:",
        "",
        _fence(docs, "json"),
        "",
        "## Answer format",
        "",
        f"Write the function calls to `{SOLUTION_FILE}` as a JSON list with one object per "
        'call: `{"tool": "<function name>", "args": {"<parameter>": <value>, ...}}`.',
    ]
    return "\n".join(parts) + "\n"


def grader_data(
    question: Mapping[str, Any], answer: Mapping[str, Any], category: str, commit: str
) -> dict[str, Any]:
    """``grader/bfcl_task.json``: what the driver passes to ``ast_checker``."""
    return {
        "id": question["id"],
        "category": category,
        "language": LANGUAGE,
        "model_name": CHECKER_MODEL,
        "source_commit": commit,
        "function": question["function"],
        "ground_truth": answer["ground_truth"],
    }


def _toml_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def task_toml(
    question: Mapping[str, Any], answer: Mapping[str, Any], category: str, commit: str
) -> str:
    """``task.toml`` of one entry (toybench kind ``data``, third-party, pinned source)."""
    q_rel, a_rel = data_paths(category)
    record = canonical_json({"question": question, "possible_answer": answer})
    top: dict[str, str | int | bool] = {
        "id": str(question["id"]),
        "benchmark": BENCHMARK,
        "kind": "data",
        "third_party": True,
        "timeout_s": TASK_TIMEOUT_S,
    }
    tables: dict[str, dict[str, str | int | bool]] = {
        "solution": {"entry": RUN_SOLUTION},
        "grader": {"entry": GRADER_ENTRY},
        "metadata": {
            "benchmark": BENCHMARK,
            "category": category,
            "original_id": str(question["id"]),
            "source_repo": REPO_URL.removesuffix(".git"),
            "source_commit": commit,
            "source_path": f"{BFCL_DIR}/{q_rel.as_posix()}",
            "answer_path": f"{BFCL_DIR}/{a_rel.as_posix()}",
            "record_sha256": sha256_text(record),
            "license": LICENSE,
            "reference_from_grader_data": True,
            "reference_source": "possible_answer",
            "checker_model": CHECKER_MODEL,
        },
    }
    lines = [f"{k} = {_toml_value(v)}" for k, v in top.items()]
    for name, table in tables.items():
        lines += ["", f"[{name}]", *(f"{k} = {_toml_value(v)}" for k, v in table.items())]
    return "\n".join(lines) + "\n"


def task_files(
    question: Mapping[str, Any], answer: Mapping[str, Any], category: str, commit: str
) -> dict[str, str]:
    """Every file of one task directory, relative path to text."""
    calls = reference_calls(question["function"], answer["ground_truth"])
    data = grader_data(question, answer, category, commit)
    return {
        "task.toml": task_toml(question, answer, category, commit),
        "instruction.md": instruction(question),
        f"solution/{SOLUTION_FILE}": json.dumps(calls, indent=2) + "\n",
        f"support/{RUN_SOLUTION}": RUN_SOLUTION_SH,
        f"grader/{GRADER_ENTRY}": GRADE_SH,
        f"grader/{DRIVER_FILE}": Path(bfcl_driver.__file__).read_text(encoding="utf-8"),
        f"grader/{TASK_DATA}": json.dumps(data, indent=2, ensure_ascii=False) + "\n",
    }


def _write_task(task_dir: Path, files: Mapping[str, str]) -> None:
    if task_dir.exists():
        shutil.rmtree(task_dir)
    for rel, text in files.items():
        path = task_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        if rel.endswith((".sh", ".py")):
            path.chmod(0o755)


def convert(
    source_root: Path,
    out_dir: Path,
    categories: Sequence[str] = CATEGORIES,
    commit: str = PINNED_COMMIT,
) -> dict[str, list[Path]]:
    """Write one task directory per entry of ``categories``; returns them by category.

    ``source_root`` is the gorilla checkout from :func:`fetch` or its BFCL directory;
    ``commit`` is recorded in every task and must match the checkout's detached ``HEAD``
    when there is one. Raises ValueError for unknown or repeated categories or a
    mismatched commit, and FileExistsError if ``out_dir`` already holds task directories
    that this conversion does not write, because the toybench loader would load them too.
    """
    if not categories or len(set(categories)) != len(categories):
        raise ValueError("categories must be non-empty and distinct")
    root = bfcl_root(source_root)
    head = bfcl_driver.checkout_commit(root)
    if head is not None and head != commit:
        raise ValueError(f"{root} is at commit {head}, not {commit}")
    records = {c: read_records(source_root, c) for c in categories}
    ids = {str(q["id"]) for pairs in records.values() for q, _ in pairs}
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = sorted(
        d.name for d in out_dir.iterdir() if (d / "task.toml").exists() and d.name not in ids
    )
    if stale:
        raise FileExistsError(
            f"{out_dir} holds {len(stale)} task directories that this conversion does not "
            f"write, for example {stale[0]}"
        )
    written: dict[str, list[Path]] = {}
    for category, pairs in records.items():
        written[category] = []
        for q, a in pairs:
            task_dir = out_dir / str(q["id"])
            _write_task(task_dir, task_files(q, a, category, commit))
            written[category].append(task_dir)
    return written


# -------------------------------------------------------------------- reference check


@dataclass(frozen=True)
class ReferenceCheck:
    """How one task's grader treated the unmodified reference over repeated runs."""

    task_id: str
    category: str
    determinism: Determinism
    exit_status: int
    """Grader exit status of the last run."""
    result: str
    """Grader output of the last run (the driver's JSON line, or its error message)."""


def check_references(
    tasks_dir: Path,
    sandbox: Sandbox,
    env: Mapping[str, str],
    repeat: int = 1,
    cache_dir: Path | None = None,
) -> list[ReferenceCheck]:
    """Grade every converted reference ``repeat`` times with :meth:`Runner.precheck`.

    ``env`` is the adapter's ``extra_env`` (``GP_BFCL_ROOT``, optionally
    ``GP_BFCL_PYTHON``). Tasks are third-party, so the Runner refuses a sandbox that
    does not isolate writes. Results are ordered by category, then task id.
    """
    adapter = ToybenchAdapter(extra_env=dict(env))
    runner = Runner(adapter, sandbox, cache_dir=cache_dir)
    checks = []
    for task in adapter.load(tasks_dir):
        det, runs = runner.precheck(task, repeat)
        last = runs[-1].grade
        result = (last.stdout.strip() or last.stderr.strip()).splitlines()
        checks.append(
            ReferenceCheck(
                task.id,
                str(task.metadata.get("category", "")),
                det,
                last.exit_status,
                result[-1] if result else "",
            )
        )
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return sorted(checks, key=lambda c: (order.get(c.category, len(order)), _id_key(c.task_id)))


def _id_key(task_id: str) -> tuple[Any, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", task_id))


def summarize(checks: Sequence[ReferenceCheck]) -> list[str]:
    """Report lines: per category, how many references pass stably, and the others by id."""
    lines = []
    for category in [*CATEGORIES, *sorted({c.category for c in checks} - set(CATEGORIES))]:
        mine = [c for c in checks if c.category == category]
        if not mine:
            continue
        bad = [c for c in mine if c.determinism is not Determinism.STABLE_PASS]
        lines.append(f"{category}: {len(mine) - len(bad)} of {len(mine)} references pass")
        lines += [
            f"  {c.task_id} {c.determinism.value} exit {c.exit_status}: {c.result}" for c in bad
        ]
    total_bad = sum(c.determinism is not Determinism.STABLE_PASS for c in checks)
    lines.append(f"all: {len(checks) - total_bad} of {len(checks)} references pass")
    return lines


# ------------------------------------------------------------------------ command line


def _cmd_check(args: argparse.Namespace) -> int:
    sandbox = best_sandbox()
    if sandbox is None:
        print("bfcl: no write-isolating sandbox (bubblewrap) works here", file=sys.stderr)
        return 1
    env = {ENV_ROOT: str(Path(args.root).resolve())}
    if args.python:
        env[ENV_PYTHON] = args.python
    checks = check_references(args.tasks, sandbox, env, args.repeat, args.cache)
    for line in summarize(checks):
        print(line)
    print(f"sandbox {sandbox.name}, {args.repeat} run(s) per reference")
    ok = all(c.determinism is Determinism.STABLE_PASS for c in checks)
    return 0 if checks and ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Command line: ``fetch``, ``convert``, or ``check``; returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="python -m graderproof.adapters.bfcl",
        description="Fetch the pinned BFCL checkout, convert its Python AST categories into "
        "toybench tasks, and check that every reference passes its grader.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch", help="check out gorilla at the pinned commit")
    p_fetch.add_argument("dest", type=Path)
    p_convert = sub.add_parser("convert", help="write one toybench task directory per entry")
    p_convert.add_argument("src", type=Path, help="the checkout from fetch")
    p_convert.add_argument("out", type=Path)
    p_convert.add_argument(
        "--categories", default=",".join(CATEGORIES), help="comma-separated (default: all eight)"
    )
    p_check = sub.add_parser("check", help="grade every converted reference under bubblewrap")
    p_check.add_argument("tasks", type=Path, help="directory of converted tasks")
    p_check.add_argument("--root", required=True, help=f"{ENV_ROOT}: the BFCL directory")
    p_check.add_argument("--python", help=f"{ENV_PYTHON}: interpreter for the checker")
    p_check.add_argument("--repeat", type=int, default=1, help="runs per reference")
    p_check.add_argument("--cache", type=Path, help="Runner cache directory")
    args = parser.parse_args(argv)
    if args.command == "check" and args.repeat < 1:
        parser.error("--repeat must be at least 1")
    try:
        if args.command == "fetch":
            root = fetch(args.dest)
            print(root)
            print(f"{ENV_ROOT}={root.resolve()}")
            return 0
        if args.command == "check":
            return _cmd_check(args)
        cats = [c for c in args.categories.split(",") if c]
        written = convert(args.src, args.out, cats)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"bfcl: {exc}", file=sys.stderr)
        return 1
    for category, dirs in written.items():
        print(f"{category}: {len(dirs)} tasks")
    print(f"converted {sum(len(d) for d in written.values())} BFCL tasks into {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
