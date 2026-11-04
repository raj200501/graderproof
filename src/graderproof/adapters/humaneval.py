"""HumanEval adapter: openai/human-eval problems as toybench ``module`` tasks (D18, D19).

HumanEval is the Docker-free substitute for Terminal-Bench 2.0 (DECISIONS.md D18).
Following D19, each problem becomes a toybench task directory, so the toybench adapter
loads and executes it and caching, sandboxing, requirement checks, and variant
operators are shared::

    HumanEval-<n>/
      task.toml               kind = "module", third_party = true, [metadata]
      instruction.md          the HumanEval prompt and where the solution goes
      solution/solution.py    prompt + canonical_solution (the reference)
      grader/grade.py         HumanEval's own check, with the test code embedded

The grader reproduces ``check_correctness()`` of ``human_eval/execution.py`` at
:data:`PINNED_COMMIT`. The program is ``solution.py`` in the working directory (for a
HumanEval sample, prompt + completion). As upstream does, a forked child process
changes into an empty temporary directory, applies ``reliability_guard()``, swallows
standard I/O, and within :data:`CHECK_TIMEOUT_S` seconds executes the program, the
test code, and ``check(<entry_point>)``, joined by newlines, in a fresh namespace. The
result string is ``passed``, ``failed: <exception>``, or ``timed out``. The grader
prints it as one JSON line and exits 0 exactly when it is ``passed``. It uses only the
standard library, imports numpy first when it is installed, and reads no file but
``solution.py``. Like upstream's ``evaluate_functional_correctness()``, it has numpy
imported before it forks, so a program that imports numpy behaves as it does there
(DECISIONS.md D29); tqdm and fire, which upstream's entry points also load, are not
preloaded. docs/adapters/humaneval.md lists every difference from upstream.

Usage::

    python -m graderproof.adapters.humaneval fetch runs/humaneval/src
    python -m graderproof.adapters.humaneval convert runs/humaneval/src runs/humaneval/tasks
    python -m graderproof.adapters.humaneval check runs/humaneval/tasks --repeat 3
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, canonical_json, sha256_text
from graderproof.run import Runner
from graderproof.sandbox import Sandbox, best_sandbox

BENCHMARK = "humaneval"
REPO_URL = "https://github.com/openai/human-eval.git"
PINNED_COMMIT = "b9453e8f1865df0a0057a1383767caa400acfbcf"
"""The merge of openai/human-eval pull request #70 (the deprecation notice), committed
2026-10-16; still the head of ``master`` on 2026-11-04. ``human_eval/execution.py`` last
changed in commit 37c4dd6 (2025-01-16) and ``data/HumanEval.jsonl.gz`` in the first
commit, 463c980 (authored 2021-07-06)."""
DATA_PATH = "data/HumanEval.jsonl.gz"
DATA_SHA256 = "b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef"
"""SHA-256 of ``data/HumanEval.jsonl.gz`` at :data:`PINNED_COMMIT` (164 problems)."""
LICENSE = "MIT"
FIELDS = ("task_id", "prompt", "canonical_solution", "test", "entry_point")
SOLUTION_MODULE = "solution"
SOLUTION_FILE = f"{SOLUTION_MODULE}.py"
GRADER_ENTRY = "grade.py"
CHECK_TIMEOUT_S = 3.0
"""HumanEval's time limit per check: the ``timeout`` default of
``evaluate_functional_correctness()`` and of its command line. As upstream, the parent
process waits at most this plus one second for the child's result."""
TASK_TIMEOUT_S = 20
"""toybench's wall-clock limit for the whole grader process (interpreter start, the
check, and the parent's wait of :data:`CHECK_TIMEOUT_S` plus one second), with slack
for a loaded machine."""
MAX_RESULT_CHARS = 2000
"""The printed result string is cut to this length; the verdict uses the full string."""
STRATUM_CUTS = (335, 475)
"""Prompt length cut points in characters (short below the first, long from the second).
On the pinned data file they split the 164 problems as evenly as three groups allow."""
GZIP_MAGIC = b"\x1f\x8b"
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

UPSTREAM_NOTICE = """\
The MIT License

Copyright (c) OpenAI (https://openai.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
"""openai/human-eval's LICENSE. The grader template below copies most of
``human_eval/execution.py``, so this notice is kept here and in every generated grader."""

_GRADER_IMPORTS = """\
import contextlib
import faulthandler
import io
import json
import multiprocessing
import os
import platform
import signal
import sys
import tempfile
import time
from typing import Optional

try:  # upstream's evaluation.py imports numpy before any check forks (DECISIONS.md D29)
    import numpy  # noqa: F401
except ImportError:
    pass
"""

# The grader body. unsafe_execute() and check_correctness() are adapted from upstream as
# docs/adapters/humaneval.md lists. Every other function and class has upstream's syntax
# tree (two "type: ignore" comments are dropped) except one line of reliability_guard():
# help is disabled through the builtins module, because a generated grader runs as
# __main__, whose __builtins__ is a module, not a dict. tests/contract/test_humaneval.py
# compares the trees with the recorded upstream file.
_GRADER_BODY = r'''

def unsafe_execute(program: str, timeout: float, conn):
    with create_tempdir():

        # These system calls are needed when cleaning up tempdir.
        import os
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        chdir = os.chdir

        # Disable functionalities that can make destructive changes to the test.
        reliability_guard()

        # Construct the check program and run it.
        check_program = program + "\n" + TEST + "\n" + f"check({ENTRY_POINT})"

        try:
            exec_globals = {}
            with swallow_io():
                with time_limit(timeout):
                    exec(check_program, exec_globals)
            result = "passed"
        except TimeoutException:
            result = "timed out"
        except BaseException as e:
            result = f"failed: {e}"
        conn.send_bytes(result.encode("utf-8", "surrogatepass"))

        # Needed for cleaning up.
        shutil.rmtree = rmtree
        os.rmdir = rmdir
        os.chdir = chdir


def check_correctness(program: str, timeout: float) -> str:
    """The result string for one program, as upstream's check_correctness() computes it."""
    ctx = multiprocessing.get_context("fork")
    receiver, sender = ctx.Pipe(duplex=False)
    p = ctx.Process(target=unsafe_execute, args=(program, timeout, sender))
    p.start()
    sender.close()
    deadline = time.monotonic() + timeout + 1
    result = []
    if receiver.poll(timeout + 1):
        try:
            result.append(receiver.recv_bytes().decode("utf-8", "surrogatepass"))
        except (EOFError, OSError, UnicodeDecodeError):
            pass
    p.join(timeout=max(0.0, deadline - time.monotonic()))
    if p.is_alive():
        p.kill()
        p.join()

    if not result:
        result.append("timed out")

    return result[0]


@contextlib.contextmanager
def time_limit(seconds: float):
    def signal_handler(signum, frame):
        raise TimeoutException("Timed out!")

    signal.setitimer(signal.ITIMER_REAL, seconds)
    signal.signal(signal.SIGALRM, signal_handler)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


@contextlib.contextmanager
def swallow_io():
    stream = WriteOnlyStringIO()
    with contextlib.redirect_stdout(stream):
        with contextlib.redirect_stderr(stream):
            with redirect_stdin(stream):
                yield


@contextlib.contextmanager
def create_tempdir():
    with tempfile.TemporaryDirectory() as dirname:
        with chdir(dirname):
            yield dirname


class TimeoutException(Exception):
    pass


class WriteOnlyStringIO(io.StringIO):
    """StringIO that throws an exception when it's read from"""

    def read(self, *args, **kwargs):
        raise IOError

    def readline(self, *args, **kwargs):
        raise IOError

    def readlines(self, *args, **kwargs):
        raise IOError

    def readable(self, *args, **kwargs):
        """Returns True if the IO object can be read."""
        return False


class redirect_stdin(contextlib._RedirectStream):
    _stream = "stdin"


@contextlib.contextmanager
def chdir(root):
    if root == ".":
        yield
        return
    cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    except BaseException as exc:
        raise exc
    finally:
        os.chdir(cwd)


def reliability_guard(maximum_memory_bytes: Optional[int] = None):
    """
    This disables various destructive functions and prevents the generated code
    from interfering with the test (e.g. fork bomb, killing other processes,
    removing filesystem files, etc.)

    WARNING
    This function is NOT a security sandbox. Untrusted code, including, model-
    generated code, should not be blindly executed outside of one. See the
    Codex paper for more information about OpenAI's code sandbox, and proceed
    with caution.
    """

    if maximum_memory_bytes is not None:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (maximum_memory_bytes, maximum_memory_bytes))
        resource.setrlimit(resource.RLIMIT_DATA, (maximum_memory_bytes, maximum_memory_bytes))
        if not platform.uname().system == "Darwin":
            resource.setrlimit(resource.RLIMIT_STACK, (maximum_memory_bytes, maximum_memory_bytes))

    faulthandler.disable()

    import builtins

    builtins.exit = None
    builtins.quit = None

    import os

    os.environ["OMP_NUM_THREADS"] = "1"

    os.kill = None
    os.system = None
    os.putenv = None
    os.remove = None
    os.removedirs = None
    os.rmdir = None
    os.fchdir = None
    os.setuid = None
    os.fork = None
    os.forkpty = None
    os.killpg = None
    os.rename = None
    os.renames = None
    os.truncate = None
    os.replace = None
    os.unlink = None
    os.fchmod = None
    os.fchown = None
    os.chmod = None
    os.chown = None
    os.chroot = None
    os.fchdir = None
    os.lchflags = None
    os.lchmod = None
    os.lchown = None
    os.getcwd = None
    os.chdir = None

    import shutil

    shutil.rmtree = None
    shutil.move = None
    shutil.chown = None

    import subprocess

    subprocess.Popen = None

    builtins.help = None

    import sys

    sys.modules["ipdb"] = None
    sys.modules["joblib"] = None
    sys.modules["resource"] = None
    sys.modules["psutil"] = None
    sys.modules["tkinter"] = None


def main() -> int:
    """Grade SOLUTION_FILE in the working directory; the exit status is 0 iff it passed."""
    try:
        with open(SOLUTION_FILE, encoding="utf-8", newline="") as fh:
            program = fh.read()
    except (OSError, ValueError) as e:
        result = f"failed: {e}"
    else:
        result = check_correctness(program, TIMEOUT)
    passed = result == "passed"
    print(json.dumps({"task_id": TASK_ID, "passed": passed, "result": result[:MAX_RESULT_CHARS]}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
'''


def task_dir_name(task_id: str) -> str:
    """Directory name and toybench id of a task: ``HumanEval/0`` becomes ``HumanEval-0``."""
    name = task_id.replace("/", "-")
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(f"task_id {task_id!r} does not give a safe directory name")
    return name


def _check_problem(record: object, where: str) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ValueError(f"{where}: record is not a JSON object")
    missing = [f for f in FIELDS if f not in record]
    if missing:
        raise ValueError(f"{where}: missing fields {missing}")
    if not all(isinstance(record[f], str) for f in FIELDS):
        raise ValueError(f"{where}: every field must be a string")
    problem = {f: str(record[f]) for f in FIELDS}
    for f, text in problem.items():
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{where}: field {f} cannot be written as UTF-8 ({exc})") from exc
    task_dir_name(problem["task_id"])
    if not problem["entry_point"].isidentifier():
        raise ValueError(f"{where}: entry_point {problem['entry_point']!r} is not an identifier")
    return problem


def read_problems(path: Path) -> list[dict[str, str]]:
    """HumanEval problems from a ``.jsonl.gz`` or plain ``.jsonl`` file, in file order.

    Blank lines are skipped, as in ``human_eval.data.stream_jsonl``. Raises ValueError,
    naming the line, on a line that is not UTF-8 JSON, a malformed record, or a duplicate
    ``task_id``.
    """
    data = path.read_bytes()
    if data[:2] == GZIP_MAGIC:
        data = gzip.decompress(data)
    problems: list[dict[str, str]] = []
    seen: set[str] = set()
    for n, raw in enumerate(data.split(b"\n"), start=1):
        try:
            line = raw.decode("utf-8")
            if not line.strip():
                continue
            record = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"{path}:{n}: not a UTF-8 JSON line ({exc})") from exc
        problem = _check_problem(record, f"{path}:{n}")
        if problem["task_id"] in seen:
            raise ValueError(f"{path}:{n}: duplicate task_id {problem['task_id']!r}")
        seen.add(problem["task_id"])
        problems.append(problem)
    return problems


def stratum(prompt: str) -> str:
    """Sampling stratum by prompt length (:data:`STRATUM_CUTS`): short, medium, or long."""
    short_max, medium_max = STRATUM_CUTS
    if len(prompt) < short_max:
        return "prompt-short"
    if len(prompt) < medium_max:
        return "prompt-medium"
    return "prompt-long"


def record_sha256(problem: Mapping[str, str]) -> str:
    """SHA-256 of a record's canonical JSON (its five fields), to trace a task to its source."""
    return sha256_text(canonical_json({f: problem[f] for f in FIELDS}))


def _fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def instruction(problem: Mapping[str, str]) -> str:
    """The task text the agent sees: the HumanEval prompt and where the solution goes."""
    ep, prompt = problem["entry_point"], problem["prompt"]
    fence = _fence(prompt)
    newline = "" if prompt.endswith("\n") else "\n"
    return (
        f"Complete the Python function `{ep}` below so that it does what its docstring "
        "describes.\n\n"
        f"Write the complete program to the file `{SOLUTION_FILE}`. It must define `{ep}` "
        "at module level. Start the file with the code below as given (its imports, any "
        f"helper functions, and the signature and docstring of `{ep}`), then write the "
        f"body of `{ep}`.\n\n"
        f"{fence}python\n{prompt}{newline}{fence}\n"
    )


def reference_solution(problem: Mapping[str, str]) -> str:
    """The reference ``solution.py``: the prompt followed by the canonical solution."""
    return problem["prompt"] + problem["canonical_solution"]


def _py_literal(text: str) -> str:
    """A Python literal for ``text``: raw triple-quoted when it reads back exactly, else repr."""
    if "'''" not in text and "\r" not in text and not text.endswith(("\\", "'")):
        candidate = "r'''" + text + "'''"
        try:
            candidate.encode("utf-8")
            if ast.literal_eval(candidate) == text:
                return candidate
        except (SyntaxError, ValueError, UnicodeEncodeError):
            pass
    return repr(text)


def _comment(text: str) -> str:
    return "".join(f"# {line}".rstrip() + "\n" for line in text.splitlines())


def grader_source(problem: Mapping[str, str]) -> str:
    """``grader/grade.py``: HumanEval's ``check_correctness`` with the test code verbatim.

    Raises ValueError on a malformed problem; in particular the entry point must be an
    identifier, because the grader runs ``check(<entry_point>)`` as code.
    """
    checked = _check_problem(dict(problem), "grader_source")
    task_id, ep = checked["task_id"], checked["entry_point"]
    doc = (
        f'"""HumanEval grader for {task_id}, generated by graderproof.adapters.humaneval.\n\n'
        "Reproduces check_correctness() of human_eval/execution.py in openai/human-eval at\n"
        f"commit {PINNED_COMMIT}. The program is {SOLUTION_FILE} in the\n"
        "working directory (for a HumanEval sample, prompt + completion). As upstream, a\n"
        "child process changes into an empty temporary directory, applies\n"
        "reliability_guard(), swallows standard I/O, and within TIMEOUT seconds executes\n"
        "the program, TEST, and check(ENTRY_POINT), joined by newlines, in a fresh\n"
        'namespace. The result is "passed", "failed: <exception>", or "timed out". It is\n'
        'printed as one JSON line, and the exit status is 0 iff it is "passed".\n'
        '"""\n\n'
    )
    notice = (
        "# Most of this file is copied from human_eval/execution.py of openai/human-eval\n"
        f"# ({REPO_URL}, commit {PINNED_COMMIT[:12]}), under this license:\n#\n"
        + _comment(UPSTREAM_NOTICE)
        + "\n"
    )
    constants = (
        f"\nTASK_ID = {task_id!r}\n"
        f"ENTRY_POINT = {ep!r}\n"
        f"SOLUTION_FILE = {SOLUTION_FILE!r}\n"
        f"TIMEOUT = {CHECK_TIMEOUT_S!r}\n"
        f"MAX_RESULT_CHARS = {MAX_RESULT_CHARS!r}\n"
        f"TEST = {_py_literal(checked['test'])}\n"
    )
    return doc + notice + _GRADER_IMPORTS + constants + _GRADER_BODY


def _toml_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def task_toml(problem: Mapping[str, str]) -> str:
    """``task.toml`` for one problem (toybench kind ``module``, third-party, pinned source)."""
    top: dict[str, str | int | bool] = {
        "id": task_dir_name(problem["task_id"]),
        "benchmark": BENCHMARK,
        "kind": "module",
        "third_party": True,
        "timeout_s": TASK_TIMEOUT_S,
    }
    tables: dict[str, dict[str, str | int | bool]] = {
        "solution": {"module": SOLUTION_MODULE},
        "grader": {"entry": GRADER_ENTRY},
        "metadata": {
            "benchmark": BENCHMARK,
            "original_id": problem["task_id"],
            "entry_point": problem["entry_point"],
            "source_repo": REPO_URL,
            "source_commit": PINNED_COMMIT,
            "source_path": DATA_PATH,
            "source_sha256": DATA_SHA256,
            "record_sha256": record_sha256(problem),
            "license": LICENSE,
            "stratum": stratum(problem["prompt"]),
            "prompt_chars": len(problem["prompt"]),
        },
    }
    lines = [f"{k} = {_toml_value(v)}" for k, v in top.items()]
    for name, table in tables.items():
        lines += ["", f"[{name}]", *(f"{k} = {_toml_value(v)}" for k, v in table.items())]
    return "\n".join(lines) + "\n"


def write_task(problem: Mapping[str, str], out_dir: Path) -> Path:
    """Write one toybench task directory under ``out_dir``, replacing an old copy."""
    checked = _check_problem(dict(problem), "write_task")
    task_dir = out_dir / task_dir_name(checked["task_id"])
    if task_dir.exists():
        shutil.rmtree(task_dir)
    (task_dir / "solution").mkdir(parents=True)
    (task_dir / "grader").mkdir()
    files = {
        "task.toml": task_toml(checked),
        "instruction.md": instruction(checked),
        f"solution/{SOLUTION_FILE}": reference_solution(checked),
        f"grader/{GRADER_ENTRY}": grader_source(checked),
    }
    for rel, text in files.items():
        (task_dir / rel).write_text(text, encoding="utf-8", newline="")
    return task_dir


def convert(jsonl_gz_path: Path, out_dir: Path) -> list[Path]:
    """Convert every problem in a HumanEval data file; returns the task directories.

    Raises ValueError if two task ids give the same directory name, and
    FileExistsError if ``out_dir`` already holds task directories that are not problems
    of this file, because the toybench loader would pick them up too. Both checks run
    before anything is written.
    """
    problems = read_problems(jsonl_gz_path)
    names: dict[str, str] = {}
    for p in problems:
        name = task_dir_name(p["task_id"])
        if name in names:
            raise ValueError(
                f"{jsonl_gz_path}: task ids {names[name]!r} and {p['task_id']!r} "
                f"both give the directory name {name!r}"
            )
        names[name] = p["task_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = sorted(
        d.name for d in out_dir.iterdir() if (d / "task.toml").exists() and d.name not in names
    )
    if stale:
        raise FileExistsError(
            f"{out_dir} holds {len(stale)} task directories that are not in "
            f"{jsonl_gz_path}, for example {stale[0]}"
        )
    return [write_task(p, out_dir) for p in problems]


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_data(path: Path) -> None:
    """Raise ValueError unless ``path`` is the pinned ``HumanEval.jsonl.gz``."""
    got = sha256_file(path)
    if got != DATA_SHA256:
        raise ValueError(f"{path}: SHA-256 {got} is not the pinned {DATA_SHA256}")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[-500:]}")
    return proc


def fetch(dest: Path) -> Path:
    """Shallow-clone openai/human-eval into ``dest`` at :data:`PINNED_COMMIT`.

    Reuses an existing checkout in ``dest``. Verifies the checked-out commit and the
    data file's SHA-256, and returns the path of ``data/HumanEval.jsonl.gz``. No code
    from the repository is run.
    """
    if not (dest / ".git").exists():
        if dest.exists() and any(dest.iterdir()):
            raise FileExistsError(f"{dest} exists and is not a git checkout")
        _git("clone", "--quiet", "--depth", "1", REPO_URL, str(dest))
    repo = str(dest)
    if _git("-C", repo, "cat-file", "-e", f"{PINNED_COMMIT}^{{commit}}", check=False).returncode:
        _git("-C", repo, "fetch", "--quiet", "--depth", "1", "origin", PINNED_COMMIT)
    _git("-C", repo, "checkout", "--quiet", "--detach", PINNED_COMMIT)
    head = _git("-C", repo, "rev-parse", "HEAD").stdout.strip()
    if head != PINNED_COMMIT:
        raise RuntimeError(f"{dest}: HEAD is {head}, expected {PINNED_COMMIT}")
    data = dest / DATA_PATH
    verify_data(data)
    return data


@dataclass(frozen=True)
class ReferenceCheck:
    """How one task's grader treated the unmodified reference over repeated runs."""

    task_id: str
    determinism: Determinism
    result: str
    """The grader's output line from the last run."""


def check_references(
    tasks_dir: Path, sandbox: Sandbox, repeat: int = 1, cache_dir: Path | None = None
) -> list[ReferenceCheck]:
    """Grade every converted reference ``repeat`` times (the :class:`Runner` precheck).

    Tasks are third-party, so the Runner refuses a sandbox that does not isolate writes.
    The result is in task order (``HumanEval-2`` before ``HumanEval-10``).
    """
    adapter = ToybenchAdapter()
    runner = Runner(adapter, sandbox, cache_dir=cache_dir)
    checks = []
    for task in adapter.load(tasks_dir):
        det, runs = runner.precheck(task, repeat)
        checks.append(ReferenceCheck(task.id, det, runs[-1].grade.stdout.strip()))
    return sorted(checks, key=lambda c: (len(c.task_id), c.task_id))


def _cmd_check(tasks_dir: Path, repeat: int, cache_dir: Path | None) -> int:
    sandbox = best_sandbox()
    if sandbox is None:
        print("humaneval: no write-isolating sandbox (bubblewrap) works here", file=sys.stderr)
        return 1
    checks = check_references(tasks_dir, sandbox, repeat, cache_dir)
    for c in checks:
        print(f"{c.task_id} {c.determinism.value} {c.result}")
    counts = Counter(c.determinism for c in checks)
    summary = ", ".join(f"{counts[d]} {d.value}" for d in Determinism)
    print(f"{len(checks)} tasks, {repeat} runs each, sandbox {sandbox.name}: {summary}")
    other = [c.task_id for c in checks if c.determinism is not Determinism.STABLE_PASS]
    print("not stable_pass: " + (" ".join(other) if other else "none"))
    return 0 if checks and not other else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Command line: ``fetch``, ``convert``, or ``check``; returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="python -m graderproof.adapters.humaneval",
        description="Fetch the pinned HumanEval data, convert it into toybench tasks, "
        "and check that every reference passes its grader.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_fetch = sub.add_parser("fetch", help="clone openai/human-eval at the pinned commit")
    p_fetch.add_argument("dest", type=Path)
    p_convert = sub.add_parser("convert", help="write one toybench task directory per problem")
    p_convert.add_argument("src", type=Path, help="the pinned checkout or its HumanEval.jsonl.gz")
    p_convert.add_argument("out", type=Path)
    p_check = sub.add_parser("check", help="grade every converted reference under bubblewrap")
    p_check.add_argument("tasks", type=Path, help="directory of converted tasks")
    p_check.add_argument("--repeat", type=int, default=1, help="runs per reference")
    p_check.add_argument("--cache", type=Path, help="Runner cache directory")
    args = parser.parse_args(argv)
    if args.command == "check" and args.repeat < 1:
        parser.error("--repeat must be at least 1")
    try:
        if args.command == "fetch":
            print(fetch(args.dest))
            return 0
        if args.command == "check":
            return _cmd_check(args.tasks, args.repeat, args.cache)
        src = args.src / DATA_PATH if args.src.is_dir() else args.src
        verify_data(src)
        paths = convert(src, args.out)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"humaneval: {exc}", file=sys.stderr)
        return 1
    print(f"converted {len(paths)} HumanEval tasks into {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
