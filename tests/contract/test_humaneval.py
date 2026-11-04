"""Contract tests for the HumanEval adapter on recorded fixtures (offline).

The fixtures are verbatim upstream files (tests/fixtures/humaneval/README.md). HumanEval
test code, canonical solutions, and upstream's execution.py are third-party code, so
every test that runs them uses bubblewrap and is skipped where bubblewrap does not work.
The other tests run no task code at all (a scripted sandbox answers instead).
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from graderproof.adapters import humaneval
from graderproof.adapters.toybench import ToybenchAdapter
from graderproof.core import Determinism, Task, canonical_json, sha256_text
from graderproof.run import Runner, SandboxPolicyError
from graderproof.sandbox import BwrapSandbox, ExecResult, Limits, LocalSandbox, bwrap_works
from graderproof.spec import probe_key

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "humaneval"
SAMPLE = FIXTURES / "HumanEval.sample.jsonl"
UPSTREAM_EXECUTION = FIXTURES / "execution.py.txt"
TASK_IDS = ["HumanEval-23", "HumanEval-32", "HumanEval-45", "HumanEval-50", "HumanEval-51"]
SAMPLE_SHA256 = "1ed77a4e04886d83f6c10726db254ea3a27b7930b47fa2af4407c4eccaeda1bd"
EXECUTION_BLOB = "bcfd7c5d452e2dcbb1ea89317c47b9e0f1c2c4ca"
LICENSE_BLOB = "4f14854c3243516f3de1487a60f14882874d7e3a"
BWRAP = bwrap_works()
needs_bwrap = pytest.mark.skipif(not BWRAP, reason="third-party code runs only under bubblewrap")


def raw_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines()]


def by_id(task_id: str) -> dict[str, Any]:
    return next(r for r in raw_records() if r["task_id"] == task_id)


def grader_constants(source: str | bytes) -> dict[str, Any]:
    """Module-level constant assignments of a generated grade.py."""
    values: dict[str, Any] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return values


def definitions(source: str) -> dict[str, ast.stmt]:
    """Top-level functions and classes of a module, by name."""
    return {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef | ast.ClassDef)
    }


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def with_timeout(task: Task, seconds: float) -> Task:
    """A copy of ``task`` whose grader has a shorter HumanEval time limit."""
    grader = task.environment["grader_files"]["grade.py"]
    patched = grader.replace(
        f"TIMEOUT = {humaneval.CHECK_TIMEOUT_S!r}\n", f"TIMEOUT = {seconds!r}\n"
    )
    assert patched != grader
    env = {**task.environment, "grader_files": {"grade.py": patched}}
    return Task.from_dict({**task.to_dict(), "environment": env})


@dataclass
class ScriptedSandbox:
    """Answers each grader run from a script of exit statuses; no task code runs."""

    exits: dict[str, list[int]]
    name: str = "scripted"
    isolates_writes: bool = True

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        writable: Sequence[Path],
        readonly: Sequence[Path] = (),
        env: Mapping[str, str] | None = None,
        limits: Limits | None = None,
    ) -> ExecResult:
        task_id = grader_constants(Path(argv[-1]).read_text(encoding="utf-8"))["TASK_ID"]
        status = self.exits[task_id].pop(0)
        result = "passed" if status == 0 else "failed: "
        line = json.dumps({"task_id": task_id, "passed": status == 0, "result": result})
        return ExecResult(status, line + "\n", "", 0.0, False, self.name)


@pytest.fixture(scope="module")
def gz_sample(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("src") / "HumanEval.jsonl.gz"
    path.write_bytes(gzip.compress(SAMPLE.read_bytes()))
    return path


@pytest.fixture(scope="module")
def converted(gz_sample: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("tasks")
    paths = humaneval.convert(gz_sample, out)
    assert [p.name for p in paths] == TASK_IDS
    return out


@pytest.fixture(scope="module")
def tasks(converted: Path) -> dict[str, Task]:
    return {t.id: t for t in ToybenchAdapter().load(converted)}


def graded(task: Task, program: str) -> tuple[bool, dict[str, Any]]:
    """Grade ``program`` as solution.py of ``task`` under bubblewrap."""
    ex = ToybenchAdapter().execute(task, {"solution.py": program}, BwrapSandbox())
    report: dict[str, Any] = json.loads(ex.grade.stdout)
    assert report["passed"] is ex.grade.passed
    assert ex.grade.exit_status == (0 if ex.grade.passed else 1)
    return ex.grade.passed, report


# Recorded fixtures


def test_fixtures_are_the_recorded_upstream_files() -> None:
    assert hashlib.sha256(SAMPLE.read_bytes()).hexdigest() == SAMPLE_SHA256
    assert git_blob_id(UPSTREAM_EXECUTION.read_bytes()) == EXECUTION_BLOB
    license_text = (FIXTURES / "LICENSE").read_bytes()
    assert git_blob_id(license_text) == LICENSE_BLOB
    assert license_text.decode("utf-8") == humaneval.UPSTREAM_NOTICE


# Reading and conversion (no task code runs)


def test_read_problems_plain_and_gzip(gz_sample: Path) -> None:
    records = raw_records()
    assert [r["task_id"] for r in records] == [t.replace("-", "/") for t in TASK_IDS]
    assert humaneval.read_problems(SAMPLE) == records
    assert humaneval.read_problems(gz_sample) == records


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("[1]", "not a JSON object"),
        ('{"task_id": "HumanEval/1"}', "missing fields"),
        (
            '{"task_id": "HumanEval/1", "prompt": 1, "canonical_solution": "", "test": "", '
            '"entry_point": "f"}',
            "must be a string",
        ),
        (
            '{"task_id": "HumanEval/1", "prompt": "", "canonical_solution": "", "test": "", '
            '"entry_point": "not valid"}',
            "not an identifier",
        ),
        (
            '{"task_id": "../x", "prompt": "", "canonical_solution": "", "test": "", '
            '"entry_point": "f"}',
            "safe directory name",
        ),
        (
            '{"task_id": "HumanEval/1", "prompt": "\\ud800", "canonical_solution": "", '
            '"test": "", "entry_point": "f"}',
            "field prompt cannot be written as UTF-8",
        ),
        ('{"task_id": "HumanEval/1",', "bad.jsonl:2: not a UTF-8 JSON line"),
    ],
)
def test_read_problems_rejects_bad_records(tmp_path: Path, line: str, message: str) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        humaneval.read_problems(path)


def test_read_problems_rejects_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "latin1.jsonl"
    path.write_bytes(b'{"task_id": "caf\xe9"}\n')
    with pytest.raises(ValueError, match=r"latin1.jsonl:1: not a UTF-8 JSON line"):
        humaneval.read_problems(path)


def test_read_problems_rejects_duplicates_and_skips_blank_lines(tmp_path: Path) -> None:
    first = SAMPLE.read_text(encoding="utf-8").splitlines()[0]
    ok = tmp_path / "ok.jsonl"
    ok.write_text(f"\n{first}\n   \n", encoding="utf-8")
    assert [p["task_id"] for p in humaneval.read_problems(ok)] == ["HumanEval/23"]
    dup = tmp_path / "dup.jsonl"
    dup.write_text(f"{first}\n{first}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task_id"):
        humaneval.read_problems(dup)


def test_task_dir_name() -> None:
    assert humaneval.task_dir_name("HumanEval/0") == "HumanEval-0"
    assert humaneval.task_dir_name("HumanEval/163") == "HumanEval-163"
    for bad in ("", "/x", "a/../b c"):
        with pytest.raises(ValueError):
            humaneval.task_dir_name(bad)


def test_stratum_cut_points() -> None:
    short_max, medium_max = humaneval.STRATUM_CUTS
    assert humaneval.stratum("x" * (short_max - 1)) == "prompt-short"
    assert humaneval.stratum("x" * short_max) == "prompt-medium"
    assert humaneval.stratum("x" * (medium_max - 1)) == "prompt-medium"
    assert humaneval.stratum("x" * medium_max) == "prompt-long"
    strata = {r["task_id"]: humaneval.stratum(r["prompt"]) for r in raw_records()}
    assert strata == {
        "HumanEval/23": "prompt-short",
        "HumanEval/32": "prompt-long",
        "HumanEval/45": "prompt-short",
        "HumanEval/50": "prompt-short",
        "HumanEval/51": "prompt-medium",
    }


def test_record_sha256() -> None:
    rec = by_id("HumanEval/45")
    assert humaneval.record_sha256(rec) == sha256_text(canonical_json(rec))
    assert humaneval.record_sha256({**rec, "extra": "ignored"}) == humaneval.record_sha256(rec)
    assert humaneval.record_sha256({**rec, "test": rec["test"] + " "}) != (
        humaneval.record_sha256(rec)
    )


def test_instruction_states_file_and_entry_point() -> None:
    rec = by_id("HumanEval/50")
    text = humaneval.instruction(rec)
    assert "`solution.py`" in text and "`decode_shift`" in text
    assert "```python\n" + rec["prompt"] + "```\n" in text
    odd = {"entry_point": "f", "prompt": "def f():\n    '''Use ```x```.'''"}
    fenced = humaneval.instruction(odd)
    assert "````python\n" + odd["prompt"] + "\n````\n" in fenced


def test_reference_solution_is_prompt_plus_canonical() -> None:
    rec = by_id("HumanEval/23")
    assert humaneval.reference_solution(rec) == rec["prompt"] + rec["canonical_solution"]


@pytest.mark.parametrize(
    "test_code",
    [
        by_id("HumanEval/51")["test"],
        "def check(candidate):\n    assert candidate('a\\nb') == 'ab'\n",
        "def check(candidate):\n    assert candidate(''' x ''')\n",
        "def check(candidate):\n    assert candidate('\\\\')  # ends with a quote'",
        "def check(candidate):\r\n    assert candidate(1)\r\n",
        "def check(candidate):\n    assert candidate('" + chr(0) + "')\n",
        "def check(candidate):\n    assert candidate('caf" + chr(0xE9) + "') == 4\n",
        "x = 1\n\\",
    ],
)
def test_grader_source_embeds_test_verbatim(tmp_path: Path, test_code: str) -> None:
    rec = {**by_id("HumanEval/51"), "test": test_code}
    path = tmp_path / "grade.py"
    path.write_text(humaneval.grader_source(rec), encoding="utf-8", newline="")
    source = path.read_bytes()  # parsed the way the interpreter reads the file
    compile(source, "grade.py", "exec")
    consts = grader_constants(source)
    assert consts["TEST"] == test_code
    assert consts["ENTRY_POINT"] == "remove_vowels"
    assert consts["TASK_ID"] == "HumanEval/51"
    assert consts["SOLUTION_FILE"] == "solution.py"
    assert consts["TIMEOUT"] == humaneval.CHECK_TIMEOUT_S == 3.0
    assert consts["MAX_RESULT_CHARS"] == humaneval.MAX_RESULT_CHARS


def test_grader_source_is_readable_and_carries_the_license() -> None:
    rec = by_id("HumanEval/51")
    source = humaneval.grader_source(rec)
    assert "TEST = r'''" + rec["test"] + "'''\n" in source
    assert humaneval.PINNED_COMMIT in source
    for line in humaneval.UPSTREAM_NOTICE.splitlines():
        assert f"# {line}".rstrip() + "\n" in source
    assert "type: ignore" not in source
    with pytest.raises(ValueError, match="safe directory name"):
        humaneval.grader_source({**rec, "task_id": "a b"})
    with pytest.raises(ValueError, match="not an identifier"):  # it becomes check(<entry>)
        humaneval.grader_source({**rec, "entry_point": "f); print('x'"})
    with pytest.raises(ValueError, match="missing fields"):
        humaneval.grader_source({"task_id": "HumanEval/51"})


def test_grader_functions_have_upstream_syntax_trees() -> None:
    upstream_text = UPSTREAM_EXECUTION.read_text(encoding="utf-8")
    upstream = definitions(upstream_text)
    ours = definitions(humaneval.grader_source(by_id("HumanEval/23")))
    verbatim = [
        "time_limit",
        "swallow_io",
        "create_tempdir",
        "TimeoutException",
        "WriteOnlyStringIO",
        "redirect_stdin",
        "chdir",
    ]
    for name in verbatim:
        assert ast.dump(ours[name]) == ast.dump(upstream[name]), name
    adapted = upstream_text.replace('__builtins__["help"] = None', "builtins.help = None")
    assert adapted != upstream_text
    guard = definitions(adapted)["reliability_guard"]
    assert ast.dump(ours["reliability_guard"]) == ast.dump(guard)
    assert set(upstream) - set(ours) == set()
    assert set(ours) - set(upstream) == {"main"}


def test_task_toml_fields() -> None:
    rec = by_id("HumanEval/45")
    meta = tomllib.loads(humaneval.task_toml(rec))
    assert meta["id"] == "HumanEval-45"
    assert meta["benchmark"] == "humaneval"
    assert meta["kind"] == "module"
    assert meta["third_party"] is True
    assert meta["timeout_s"] == humaneval.TASK_TIMEOUT_S
    assert meta["solution"] == {"module": "solution"}
    assert meta["grader"] == {"entry": "grade.py"}
    assert meta["metadata"] == {
        "benchmark": "humaneval",
        "original_id": "HumanEval/45",
        "entry_point": "triangle_area",
        "source_repo": "https://github.com/openai/human-eval.git",
        "source_commit": "b9453e8f1865df0a0057a1383767caa400acfbcf",
        "source_path": "data/HumanEval.jsonl.gz",
        "source_sha256": humaneval.DATA_SHA256,
        "record_sha256": humaneval.record_sha256(rec),
        "license": "MIT",
        "stratum": "prompt-short",
        "prompt_chars": len(rec["prompt"]),
    }


def test_write_task_replaces_old_copy_and_validates(tmp_path: Path) -> None:
    rec = by_id("HumanEval/23")
    stale = tmp_path / "HumanEval-23" / "grader" / "stale.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("x")
    d = humaneval.write_task(rec, tmp_path)
    assert d == tmp_path / "HumanEval-23"
    assert not stale.exists()
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    assert files == ["grader/grade.py", "instruction.md", "solution/solution.py", "task.toml"]
    with pytest.raises(ValueError, match="not an identifier"):
        humaneval.write_task({**rec, "entry_point": "a-b"}, tmp_path)


def test_convert_output_matches_records(converted: Path) -> None:
    for rec in raw_records():
        d = converted / humaneval.task_dir_name(rec["task_id"])
        solution = (d / "solution" / "solution.py").read_bytes()
        assert solution == (rec["prompt"] + rec["canonical_solution"]).encode("utf-8")
        consts = grader_constants((d / "grader" / "grade.py").read_bytes())
        assert consts["TEST"] == rec["test"]
        assert consts["ENTRY_POINT"] == rec["entry_point"]
        assert consts["TASK_ID"] == rec["task_id"]
        assert rec["prompt"] in (d / "instruction.md").read_text(encoding="utf-8")


def test_convert_refuses_stale_task_directories(gz_sample: Path, tmp_path: Path) -> None:
    out = tmp_path / "tasks"
    assert len(humaneval.convert(gz_sample, out)) == len(TASK_IDS)
    assert len(humaneval.convert(gz_sample, out)) == len(TASK_IDS)  # converting again is fine
    (out / "notes").mkdir()  # not a task directory, so it is left alone
    other = out / "HumanEval-999"
    other.mkdir()
    (other / "task.toml").write_text('id = "HumanEval-999"\n')
    with pytest.raises(FileExistsError, match="HumanEval-999"):
        humaneval.convert(gz_sample, out)


def test_convert_refuses_task_ids_with_one_directory_name(tmp_path: Path) -> None:
    first = by_id("HumanEval/23")
    clash = {**first, "task_id": "HumanEval-23"}  # also gives the directory HumanEval-23
    src = tmp_path / "clash.jsonl"
    src.write_text(json.dumps(first) + "\n" + json.dumps(clash) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="both give the directory name 'HumanEval-23'"):
        humaneval.convert(src, out)
    assert not out.exists()  # refused before anything was written


def test_converted_tasks_load_as_third_party_module_tasks(
    tasks: dict[str, Task], converted: Path
) -> None:
    assert sorted(tasks) == TASK_IDS
    for t in tasks.values():
        d = converted / t.id
        assert t.benchmark == "humaneval"
        assert t.key == f"humaneval:{t.id}"
        assert t.environment["kind"] == "module"
        assert t.environment["module"] == "solution"
        assert t.environment["third_party"] is True
        assert t.environment["timeout_s"] == humaneval.TASK_TIMEOUT_S
        assert t.metadata["trusted_local"] is False
        assert t.metadata["source_commit"] == humaneval.PINNED_COMMIT
        assert t.metadata["license"] == "MIT"
        assert t.metadata["stratum"].startswith("prompt-")
        assert t.instructions == (d / "instruction.md").read_text(encoding="utf-8")
        assert t.reference_solution == {
            "solution.py": (d / "solution" / "solution.py").read_text(encoding="utf-8")
        }
        assert t.environment["grader_files"] == {
            "grade.py": (d / "grader" / "grade.py").read_text(encoding="utf-8")
        }
        assert ToybenchAdapter().mutable_files(t) == {"solution.py": "python"}


# Grading under bubblewrap (third-party code)


@needs_bwrap
def test_references_pass_their_graders(tasks: dict[str, Task]) -> None:
    for t in tasks.values():
        passed, report = graded(t, t.reference_solution["solution.py"])
        assert passed, (t.id, report)
        assert report == {"task_id": t.metadata["original_id"], "passed": True, "result": "passed"}


@needs_bwrap
def test_wrong_solutions_fail(tasks: dict[str, Task]) -> None:
    prompt = by_id("HumanEval/23")["prompt"]
    strlen = tasks["HumanEval-23"]
    assert graded(strlen, prompt + "    return 0\n") == (
        False,
        {"task_id": "HumanEval/23", "passed": False, "result": "failed: "},
    )
    assert not graded(strlen, prompt + "    return len(string) + 1\n")[0]
    passed, report = graded(strlen, prompt + "    return len(string\n")
    assert not passed and report["result"].startswith("failed: '(' was never closed")
    passed, report = graded(strlen, "")
    assert not passed and report["result"] == "failed: name 'strlen' is not defined"


@needs_bwrap
def test_missing_solution_file_fails(tasks: dict[str, Task]) -> None:
    t = tasks["HumanEval-45"]
    ex = ToybenchAdapter().execute(t, {"other.py": "x = 1\n"}, BwrapSandbox())
    assert not ex.grade.passed and ex.grade.exit_status == 1
    report = json.loads(ex.grade.stdout)
    assert report["result"] == "failed: [Errno 2] No such file or directory: 'solution.py'"


@needs_bwrap
def test_time_limit_reports_timed_out(tasks: dict[str, Task]) -> None:
    t = with_timeout(tasks["HumanEval-45"], 0.3)
    loop = by_id("HumanEval/45")["prompt"] + "    while True:\n        pass\n"
    assert graded(t, loop) == (
        False,
        {"task_id": "HumanEval/45", "passed": False, "result": "timed out"},
    )


@needs_bwrap
def test_long_results_are_cut_in_the_printed_line(tasks: dict[str, Task]) -> None:
    t = tasks["HumanEval-45"]
    program = t.reference_solution["solution.py"] + "\nraise ValueError('x' * 5000)\n"
    passed, report = graded(t, program)
    assert not passed
    assert report["result"] == ("failed: " + "x" * 5000)[: humaneval.MAX_RESULT_CHARS]


UPSTREAM_DRIVER = """\
import importlib
import json
import sys

for name in sys.argv[4:]:  # modules upstream's caller has imported before any check
    importlib.import_module(name)
sys.path.insert(0, sys.argv[1])
from execution import check_correctness

with open(sys.argv[2], encoding="utf-8") as fh:
    cases = json.load(fh)
results = [
    check_correctness(c["problem"], c["completion"], c["timeout"])["result"] for c in cases
]
with open(sys.argv[3], "w", encoding="utf-8") as fh:
    json.dump(results, fh)
"""


def upstream_results(
    cases: list[dict[str, Any]], root: Path, preload: Sequence[str] = ()
) -> list[str]:
    """Result strings of the recorded upstream ``check_correctness``, run under bubblewrap.

    ``preload`` names modules the driver imports first, as upstream's
    ``evaluate_functional_correctness()`` has numpy imported before it checks anything.
    """
    lib, ws = root / "upstream", root / "ws"
    lib.mkdir(parents=True)
    ws.mkdir()
    (lib / "execution.py").write_bytes(UPSTREAM_EXECUTION.read_bytes())
    (ws / "driver.py").write_text(UPSTREAM_DRIVER, encoding="utf-8")
    (ws / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    argv = ["python3", str(ws / "driver.py"), str(lib), str(ws / "cases.json"), str(ws / "out")]
    res = BwrapSandbox().run([*argv, *preload], cwd=ws, writable=[ws], readonly=[lib])
    assert res.exit_status == 0, res.stderr
    results: list[str] = json.loads((ws / "out").read_text(encoding="utf-8"))
    return results


def differential_cases() -> list[tuple[str, str, float]]:
    """(task id, program, time limit) cases covering every kind of result."""
    cases: list[tuple[str, str, float]] = []
    for rec in raw_records():
        prompt, ref = rec["prompt"], rec["prompt"] + rec["canonical_solution"]
        for program in (ref, prompt + "    return None\n", prompt + "    return (\n"):
            cases.append((rec["task_id"], program, 3.0))
    area = by_id("HumanEval/45")
    prompt, ref = area["prompt"], area["prompt"] + area["canonical_solution"]
    for program in (
        ref + "\nraise ValueError('boom')\n",
        ref + "\nimport sys\nsys.exit(3)\n",
        ref + "\nexit()\n",
        ref + "\nprint('noise')\n",
        ref + "\nimport os\nos._exit(0)\n",
        prompt + "    return float(input())\n",
        prompt + "    return len(open('solution.py').read())\n",
        ref + "\nraise ValueError('caf\\u00e9 \\U0001f600')\n",
        ref + "\nraise ValueError('\\ud800')\n",  # a lone surrogate must cross the pipe intact
    ):
        cases.append(("HumanEval/45", program, 3.0))
    cases.append(("HumanEval/45", prompt + "    while True:\n        pass\n", 0.3))
    shift = by_id("HumanEval/50")
    without_helper = "def decode_shift" + shift["prompt"].split("def decode_shift")[1]
    cases.append(("HumanEval/50", without_helper + shift["canonical_solution"], 3.0))
    return cases


@needs_bwrap
def test_grader_agrees_with_upstream_check_correctness(
    tasks: dict[str, Task], tmp_path: Path
) -> None:
    cases = differential_cases()
    upstream_cases = []
    for task_id, program, timeout in cases:
        rec = by_id(task_id)
        prompt = rec["prompt"] if program.startswith(rec["prompt"]) else ""
        problem = {**rec, "prompt": prompt}
        upstream_cases.append(
            {"problem": problem, "completion": program[len(prompt) :], "timeout": timeout}
        )
    expected = upstream_results(upstream_cases, tmp_path)
    ours = []
    for task_id, program, timeout in cases:
        task = tasks[humaneval.task_dir_name(task_id)]
        if timeout != humaneval.CHECK_TIMEOUT_S:
            task = with_timeout(task, timeout)
        ours.append(graded(task, program)[1]["result"])
    assert ours == expected
    kinds = {r if r in ("passed", "timed out") else r.split(":")[0] for r in expected}
    assert kinds == {"passed", "failed", "timed out"}
    assert expected.count("passed") == len(raw_records()) + 1  # references and print noise


@needs_bwrap
def test_numpy_programs_match_upstreams_evaluation(tasks: dict[str, Task], tmp_path: Path) -> None:
    """numpy is preloaded as upstream's evaluation.py has it (DECISIONS.md D29).

    upstream's evaluation.py imports numpy before any check forks; numpy's import calls
    os.putenv, which reliability_guard() disables, so only a preloaded numpy works.
    """
    probe = BwrapSandbox().run(["python3", "-c", "import numpy"], cwd=tmp_path, writable=[tmp_path])
    if probe.exit_status != 0:
        pytest.skip("the sandbox's python3 cannot import numpy")
    rec = by_id("HumanEval/23")
    body = "    import numpy\n    return int(numpy.int64(len(string)))\n"
    passed, report = graded(tasks["HumanEval-23"], rec["prompt"] + body)
    assert passed and report["result"] == "passed"
    case = {"problem": rec, "completion": body, "timeout": 3.0}
    assert upstream_results([case], tmp_path / "numpy", preload=["numpy"]) == ["passed"]
    plain = upstream_results([case], tmp_path / "plain")
    assert plain == ["failed: 'NoneType' object is not callable"]


@needs_bwrap
def test_function_call_probes_work(tasks: dict[str, Task]) -> None:
    t = tasks["HumanEval-23"]
    probe: dict[str, Any] = {"function": "strlen", "args": ["abcd"]}
    ex = ToybenchAdapter().execute(t, t.reference_solution, BwrapSandbox(), [probe])
    assert ex.outcome.probes[probe_key(probe)] == {"ok": True, "value": 4}


@needs_bwrap
def test_check_references_under_bwrap(converted: Path, tmp_path: Path) -> None:
    checks = humaneval.check_references(converted, BwrapSandbox(), repeat=2, cache_dir=tmp_path)
    assert [c.task_id for c in checks] == TASK_IDS
    for c in checks:
        assert c.determinism is Determinism.STABLE_PASS, c
        assert json.loads(c.result)["result"] == "passed"
    again = humaneval.check_references(converted, BwrapSandbox(), repeat=2, cache_dir=tmp_path)
    assert again == checks


# Runner policy and the check command (no task code runs)


def test_runner_refuses_a_sandbox_without_write_isolation(
    tasks: dict[str, Task], converted: Path
) -> None:
    t = tasks["HumanEval-23"]
    with pytest.raises(SandboxPolicyError):
        Runner(ToybenchAdapter(), LocalSandbox()).execute(t, t.reference_solution)
    with pytest.raises(SandboxPolicyError):
        humaneval.check_references(converted, LocalSandbox())


def test_check_references_classifies_and_orders(converted: Path, tmp_path: Path) -> None:
    script = ScriptedSandbox(
        {
            "HumanEval/23": [0, 0],
            "HumanEval/32": [0, 0],
            "HumanEval/45": [1, 1],
            "HumanEval/50": [0, 1],
            "HumanEval/51": [0, 0],
        }
    )
    checks = humaneval.check_references(converted, script, repeat=2)
    assert [(c.task_id, c.determinism) for c in checks] == [
        ("HumanEval-23", Determinism.STABLE_PASS),
        ("HumanEval-32", Determinism.STABLE_PASS),
        ("HumanEval-45", Determinism.STABLE_FAIL),
        ("HumanEval-50", Determinism.FLAKY),
        ("HumanEval-51", Determinism.STABLE_PASS),
    ]
    assert json.loads(checks[3].result)["result"] == "failed: "
    synthetic = tmp_path / "synthetic.jsonl"  # project-written records, never executed here
    lines = [
        json.dumps(
            {
                "task_id": f"HumanEval/{n}",
                "prompt": "def f():\n",
                "canonical_solution": "    return 1\n",
                "test": "def check(candidate):\n    assert candidate() == 1\n",
                "entry_point": "f",
            }
        )
        for n in (10, 2)
    ]
    synthetic.write_text("\n".join(lines) + "\n", encoding="utf-8")
    humaneval.convert(synthetic, tmp_path / "synthetic")
    order = ScriptedSandbox({"HumanEval/2": [0], "HumanEval/10": [0]})
    checks = humaneval.check_references(tmp_path / "synthetic", order)
    assert [c.task_id for c in checks] == ["HumanEval-2", "HumanEval-10"]


def test_main_check(
    converted: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(humaneval, "best_sandbox", lambda: None)
    assert humaneval.main(["check", str(converted)]) == 1
    assert "no write-isolating sandbox" in capsys.readouterr().err
    passing = ScriptedSandbox({t.replace("-", "/"): [0, 0] for t in TASK_IDS})
    monkeypatch.setattr(humaneval, "best_sandbox", lambda: passing)
    assert humaneval.main(["check", str(converted), "--repeat", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith('HumanEval-23 stable_pass {"task_id": "HumanEval/23"')
    assert lines[-2] == (
        "5 tasks, 2 runs each, sandbox scripted: 5 stable_pass, 0 stable_fail, 0 flaky"
    )
    assert lines[-1] == "not stable_pass: none"
    failing = ScriptedSandbox({t.replace("-", "/"): [0] for t in TASK_IDS})
    failing.exits["HumanEval/32"] = [1]
    monkeypatch.setattr(humaneval, "best_sandbox", lambda: failing)
    assert humaneval.main(["check", str(converted)]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "not stable_pass: HumanEval-32"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert humaneval.main(["check", str(empty)]) == 1
    assert "0 tasks" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        humaneval.main(["check", str(converted), "--repeat", "0"])


# fetch and the command line (git is replaced by a fake)


def test_sha256_file_and_verify_data(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert humaneval.sha256_file(SAMPLE) == digest
    with pytest.raises(ValueError, match="not the pinned"):
        humaneval.verify_data(SAMPLE)
    monkeypatch.setattr(humaneval, "DATA_SHA256", digest)
    humaneval.verify_data(SAMPLE)


class FakeGit:
    """Stands in for ``subprocess.run`` of git commands; records every call."""

    def __init__(self, data: bytes, head: str = humaneval.PINNED_COMMIT) -> None:
        self.data = data
        self.head = head
        self.have_commit = False
        self.fail: str | None = None
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd = list(argv)
        self.calls.append(cmd)
        assert cmd[0] == "git" and kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        sub = cmd[1] if cmd[1] == "clone" else cmd[3]
        if sub == self.fail:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: boom\n")
        if sub == "clone":
            dest = Path(cmd[-1])
            (dest / ".git").mkdir(parents=True)
            (dest / "data").mkdir()
            (dest / humaneval.DATA_PATH).write_bytes(self.data)
        elif sub == "cat-file":
            return subprocess.CompletedProcess(cmd, 0 if self.have_commit else 1, "", "")
        elif sub == "fetch":
            self.have_commit = True
        elif sub == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, self.head + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def subcommands(self) -> list[str]:
        return [c[1] if c[1] == "clone" else c[3] for c in self.calls]


def fake_git(monkeypatch: pytest.MonkeyPatch, gz_sample: Path, **kwargs: Any) -> FakeGit:
    data = gz_sample.read_bytes()
    monkeypatch.setattr(humaneval, "DATA_SHA256", hashlib.sha256(data).hexdigest())
    fake = FakeGit(data, **kwargs)
    monkeypatch.setattr(subprocess, "run", fake)  # the module object humaneval._git uses
    return fake


def test_fetch_clones_and_checks_out_pinned_commit(
    tmp_path: Path, gz_sample: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = fake_git(monkeypatch, gz_sample)
    dest = tmp_path / "human-eval"
    assert humaneval.fetch(dest) == dest / "data" / "HumanEval.jsonl.gz"
    assert fake.subcommands() == ["clone", "cat-file", "fetch", "checkout", "rev-parse"]
    assert fake.calls[0][-2:] == [humaneval.REPO_URL, str(dest)]
    assert "--depth" in fake.calls[0] and humaneval.PINNED_COMMIT in fake.calls[2]
    assert fake.calls[3][-2:] == ["--detach", humaneval.PINNED_COMMIT]
    fake.calls.clear()
    humaneval.fetch(dest)
    assert fake.subcommands() == ["cat-file", "checkout", "rev-parse"]


def test_fetch_refusals(tmp_path: Path, gz_sample: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fake_git(monkeypatch, gz_sample, head="0" * 40)
    with pytest.raises(RuntimeError, match="HEAD is"):
        humaneval.fetch(tmp_path / "a")
    fake.fail = "clone"
    with pytest.raises(RuntimeError, match="fatal: boom"):
        humaneval.fetch(tmp_path / "b")
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "file").write_text("x")
    with pytest.raises(FileExistsError):
        humaneval.fetch(busy)
    fake.fail, fake.head = None, humaneval.PINNED_COMMIT
    monkeypatch.setattr(humaneval, "DATA_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="not the pinned"):
        humaneval.fetch(tmp_path / "c")


def test_main_convert_and_fetch(
    tmp_path: Path,
    gz_sample: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out"
    assert humaneval.main(["convert", str(gz_sample), str(out)]) == 1
    assert "not the pinned" in capsys.readouterr().err
    checkout = tmp_path / "checkout"
    (checkout / "data").mkdir(parents=True)
    (checkout / humaneval.DATA_PATH).write_bytes(gz_sample.read_bytes())
    monkeypatch.setattr(humaneval, "DATA_SHA256", humaneval.sha256_file(gz_sample))
    assert humaneval.main(["convert", str(checkout), str(out)]) == 0
    assert "converted 5 HumanEval tasks" in capsys.readouterr().out
    assert sorted(p.name for p in out.iterdir()) == TASK_IDS
    monkeypatch.setattr(humaneval, "fetch", lambda dest: dest / humaneval.DATA_PATH)
    assert humaneval.main(["fetch", str(tmp_path / "src")]) == 0
    assert capsys.readouterr().out.strip().endswith("HumanEval.jsonl.gz")
    with pytest.raises(SystemExit):
        humaneval.main([])


def test_module_runs_as_a_program(gz_sample: Path, tmp_path: Path) -> None:
    argv = [sys.executable, "-m", "graderproof.adapters.humaneval", "convert"]
    proc = subprocess.run(
        [*argv, str(gz_sample), str(tmp_path / "out")], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 1 and "is not the pinned" in proc.stderr
    assert not (tmp_path / "out").exists()
